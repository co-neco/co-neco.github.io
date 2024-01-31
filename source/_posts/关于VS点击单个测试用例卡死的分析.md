---
title: 关于VS点击单个测试用例卡死的分析
categories:
  - Technology
  - Reverse
date: 2024-01-30 09:20:39
tags:
---

某一天，点击VS的单个测试用例时，发现卡死了，VS提示没有响应，以下是测试工程的结构：

```
Project_name
- namespace
 - test_suite_name
  - test1
  - test2    <---- 点击test2，就卡死
```

提示如下：

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/VS_deadlock_analysis/DFFC8052-EC83-4a42-BA89-E14B6A80F95E.png)

当时简单用windbg看了下，没有看出原因。因为当时可以使用命令行选项来跑单个测试用例，所以这个问题就搁置了。

之后重装了操作系统，发现没有这个卡死问题了。一段时间后，结果又出现了这个卡死。看来还是得把这个问题解决，在VS的UI测试单元测试用例还是挺实用的。

## 盲猜诱因

之前有一次停电，然后电脑没关，导致了电脑突然关机，有些进程没有及时保存各自的数据。于是怀疑是VS的缓存一致性被破坏了。

参考microsoft社区的[回答](https://learn.microsoft.com/en-us/answers/questions/1221136/visual-studio-2022-clear-local-caches)，清空了以下三部分：

> - Component Cache
>
>   Close Visual Studio (ensure devenv.exe is not present in the Task Manager) and delete the C:\Users\xxxx AppData\Local\Microsoft\VisualStudio\your version xxx\ComponentModelCache directory
>
> - Temp folder
>
>   Delete the C:\Users\xxxx \AppData\Local\Temp directory
>
> - Roslyn folder
>
>   C:\Users\xxxx\AppData\Local\Microsoft\VisualStudio\Roslyn

重启VS，结果依旧卡死。清除缓存不行，看来只能上windbg了。

## 初步分析

VS是32位的，一般启动不会有管理员权限，所以用windbg直接附加就可以分析了。

> windbg安装：windbg属于WDK的一部分，安装请参考这篇[官方文档](https://learn.microsoft.com/en-us/windows-hardware/drivers/download-the-wdk)。

因为是界面卡死，然后界面对应的线程是主线程，主线程在windbg里是0号线程，所以切过去，看下栈：

```cpp
0:051> ~0s
eax=00000000 ebx=00000002 ecx=00000000 edx=00000000 esi=00000000 edi=00000001
eip=7585586c esp=006fe590 ebp=006fe600 iopl=0         nv up ei pl nz ac pe nc
cs=0023  ss=002b  ds=002b  es=002b  fs=0053  gs=002b             efl=00200216
win32u!NtUserMsgWaitForMultipleObjectsEx+0xc:
7585586c c21400          ret     14h
0:000> kv
 # ChildEBP RetAddr  Args to Child              
00 006fe58c 75bdc37a 00000001 222d4b14 ffffffff win32u!NtUserMsgWaitForMultipleObjectsEx+0xc (FPO: [5,0,0])
01 006fe600 75bdc2ac 00000001 222d4b14 ffffffff USER32!RealMsgWaitForMultipleObjectsEx+0x7a (FPO: [Non-Fpo])
02 006fe620 5a051583 00000001 222d4b14 ffffffff USER32!MsgWaitForMultipleObjectsEx+0x4c (FPO: [Non-Fpo])
03 006fe644 750173cd 00000001 222d4b14 ffffffff vslog!VSResponsiveness::Detours::DetourMsgWaitForMultipleObjectsEx+0x45 (FPO: [Non-Fpo])
04 006fe6c4 75017074 222d4b14 00000001 006fe814 combase!CCliModalLoop::BlockFn+0x14b (FPO: [Non-Fpo]) (CONV: thiscall) [onecore\com\combase\dcomrem\callctrl.cxx @ 2156] 
05 006fe780 75016a97 00000002 ffffffff 00000001 combase!ClassicSTAThreadWaitForHandles+0xb4 (FPO: [Non-Fpo]) (CONV: stdcall) [onecore\com\combase\dcomrem\classicsta.cpp @ 51] 
06 006fe7ac 5a051a35 00000002 ffffffff 00000001 combase!CoWaitForMultipleHandles+0x77 (FPO: [Non-Fpo]) (CONV: stdcall) [onecore\com\combase\dcomrem\sync.cxx @ 122] 
07 006fe7dc 58c9056e 00000002 ffffffff 00000001 vslog!VSResponsiveness::Detours::DetourCoWaitForMultipleHandles+0x72 (FPO: [5,1,4])
08 006fe830 58c904fe 00000000 ffffffff 00000001 clr!MsgWaitHelper+0x64 (FPO: [Non-Fpo])
09 006fe8b4 58d6c4ae 00000001 222d4b14 00000000 clr!Thread::DoAppropriateWaitWorker+0x1d8 (FPO: [Non-Fpo])
0a 006fe920 58d6c5f7 00000001 222d4b14 00000000 clr!Thread::DoAppropriateWait+0x64 (FPO: [Non-Fpo])
0b 006fe96c 58bd13cc ffffffff 00000001 00000000 clr!CLREventBase::WaitEx+0x121 (FPO: [Non-Fpo])
0c 006fe984 58d57bbb ffffffff 00000001 00000000 clr!CLREventBase::Wait+0x1a (FPO: [3,0,0])
0d 006fea10 58d57cec 009e9a08 ffffffff bb93f1e9 clr!AwareLock::EnterEpilogHelper+0xa8 (FPO: [Non-Fpo])
0e 006fea58 58d57ac5 009e9a08 ffffffff 006feb48 clr!AwareLock::EnterEpilog+0x48 (FPO: [Non-Fpo])
0f 006fea70 58ca97d2 bb93f0ad 006feb48 2d87a548 clr!AwareLock::Enter+0x4a (FPO: [0,1,0])
10 006feb1c 14550bb2 179f3680 17a052a0 179f3640 clr!JITutil_MonReliableEnter+0xb5 (FPO: [Non-Fpo])
WARNING: Frame IP not in any known module. Following frames may be wrong.
11 006feb54 145508d8 17a02e6c 12e7ad50 2d94c2f0 0x14550bb2
12 006feba8 1452a5f1 04e3b530 17a05074 17a01b44 0x145508d8
13 006fecac 14529755 179f3640 173a15cc 17a017d8 0x1452a5f1
14 006fed28 55abcc3a 006fed94 55a53674 03612f48 0x14529755
15 006fed30 55a53674 03612f48 0363c814 00000000 mscorlib_ni!System.Runtime.CompilerServices.AsyncMethodBuilderCore+MoveNextRunner.InvokeMoveNext(System.Object)$##600711C+0x1a
16 006fed94 55a535a7 00000001 17a018ec 00000000 mscorlib_ni!System.Threading.ExecutionContext.RunInternal(System.Threading.ExecutionContext, System.Threading.ContextCallback, System.Object, Boolean)$##6003C30+0xc4
17 006feda8 55abcb8e 00000001 17a018ec 00000000 mscorlib_ni!System.Threading.ExecutionContext.Run(System.Threading.ExecutionContext, System.Threading.ContextCallback, System.Object, Boolean)$##6003C2F+0x17
18 006fede0 51b0e8fd 2d944b74 17a00540 179ff20c mscorlib_ni!System.Runtime.CompilerServices.AsyncMethodBuilderCore+MoveNextRunner.Run()$##600711B+0x5e
19 006fee24 51ac0c4a 5449efae 00000001 036415f0 Microsoft_VisualStudio_Threading_ni+0xce8fd
1a 006fee40 5449ee95 00000001 17a01930 00000000 Microsoft_VisualStudio_Threading_ni+0x80c4a
1b 006fee7c 544a11cd 00000000 00000001 17a01930 WindowsBase_ni+0xdee95
1c 006feec4 5449f67f 17a0194c 544a0f9b 00000000 WindowsBase_ni+0xe11cd
1d 006fef00 5449d456 ffffffff 0361fd98 00000000 WindowsBase_ni+0xdf67f
1e 006fef40 5449c57c 00000000 00000000 0361fd14 WindowsBase_ni+0xdd456
1f 006fef7c 5449e771 03620b04 00000000 00000000 WindowsBase_ni+0xdc57c
20 006fefb8 5449ea5c 03620b04 00000000 00000000 WindowsBase_ni+0xde771
21 006fefd8 5449ef52 00000001 03612f48 0361fcc4 WindowsBase_ni+0xdea5c
22 006feff0 5449ee95 00000001 03620aec 00000000 WindowsBase_ni+0xdef52
23 006ff02c 5449d072 00000000 00000001 03620aec WindowsBase_ni+0xdee95
24 006ff084 5449e5c4 00000001 03620aec 03620acc WindowsBase_ni+0xdd072
25 006ff0cc 0339d922 00000000 00000000 0000c314 WindowsBase_ni+0xde5c4
26 006ff100 75be0eab 00042904 0000c314 00000000 0x339d922
27 006ff12c 75bd7e5a 058c3d4e 00042904 0000c314 USER32!_InternalCallWinProc+0x2b
28 006ff210 75bd5bca 058c3d4e 00000000 0000c314 USER32!UserCallWinProcCheckWow+0x33a (FPO: [SEH])
29 006ff284 75bd5990 0000c214 006ff2c8 596125e0 USER32!DispatchMessageWorker+0x22a (FPO: [Non-Fpo])
2a 006ff290 596125e0 006ff2e0 f14ad7b9 05a75e5c USER32!DispatchMessageW+0x10 (FPO: [Non-Fpo])
2b 006ff2c8 59612310 006ff2e0 ffffffff 05a75e48 msenv!VStudioMain+0x202f4
2c 006ff300 59656eee f14ad65d 05a71a80 00000000 msenv!VStudioMain+0x20024
2d 006ff32c 596570bf 00000001 ffffffff f14ad61d msenv!VStudioMain+0x64c02
2e 006ff36c 59656fef 00000001 10831080 00001a24 msenv!VStudioMain+0x64dd3
2f 006ff38c 59656e86 05a71a84 00000001 ffffffff msenv!VStudioMain+0x64d03
30 006ff3b8 5965cc25 ffffffff f14ad139 006ff588 msenv!VStudioMain+0x64b9a
31 006ff448 595f2379 f14ad101 006ff588 59400000 msenv!VStudioMain+0x6a939
32 006ff470 0075112c 009ca78c 00000000 00000000 msenv!VStudioMain+0x8d
33 006ff48c 00752ae5 ddfd7951 75a42010 00764218 devenv!WriteAssertEtwEventW+0x59b1
34 006ff7d0 00754001 00000000 00754001 00000000 devenv!WriteAssertEtwEventW+0x736a
35 006ff804 00753d94 00740000 00000000 009a3cd7 devenv!WriteAssertEtwEventW+0x8886
36 006ff850 75a3fcc9 0046a000 75a3fcb0 006ff8bc devenv!WriteAssertEtwEventW+0x8619
37 006ff860 77167c6e 0046a000 c7db6fed 00000000 KERNEL32!BaseThreadInitThunk+0x19 (FPO: [Non-Fpo])
38 006ff8bc 77167c3e ffffffff 77188c0c 00000000 ntdll!__RtlUserThreadStart+0x2f (FPO: [SEH])
39 006ff8cc 00000000 00763ef2 0046a000 00000000 ntdll!_RtlUserThreadStart+0x1b (FPO: [Non-Fpo])

```

栈帧0-2的前两个参数是等待的句柄数和句柄数组：

```cpp
0:000> dd 222d4b14  l1
222d4b14  000018fc
0:000> !handle 000018fc f
Handle 18fc
  Type         	Event
  Attributes   	0
  GrantedAccess	0x1f0003:
         Delete,ReadControl,WriteDac,WriteOwner,Synch
         QueryState,ModifyState
  HandleCount  	2
  PointerCount 	34922
  Name         	<none>
  Object Specific Information
    Event Type Auto Reset
    Event is Waiting
```

可以看到这个句柄表示一个事件，且是non-signaled状态。值得注意的是这个句柄被打开了两次(HandleCount)，可猜测有一个线程获取了这个事件，而主线程在等待这个事件，结果那个线程有没有将这个事件值为signaled状态，导致死锁。

栈帧继续往下看，观察3-6，关于combase模块，从模块的函数名可看出该模块负责等待；然后栈帧3是vslog模块用inlinehook的方式劫持等待函数，用于记录等待事件，无响应的窗口弹出应该就是通过这种方式实现的，即记录等待的时间，如果超时就提示。

再观察栈帧8-16，可看到进入等待的一个流程。从17开始，就看不到模块名了，这是因为.net程序的托管代码需要通过clr模块的jit化，编译成机器码（汇编代码）才能执行，所以这一片内存是clr专门为动态jit化的代码分配的内存，所以看不到模块信息。

栈帧再往后就是一些.net模块的栈，其中可看到一些C#的函数，不过都属于框架的东西、多线程异步调用，没有太多参考内容。

观察其他线程的信息，没找到相关有用的信息，那现在的线索就只有主线程的等待流程了，即栈帧8-16了。

## 等待流程分析

为方便阅读，这里把栈帧8-16单独提出来

```cpp
08 006fe830 58c904fe 00000000 ffffffff 00000001 clr!MsgWaitHelper+0x64 (FPO: [Non-Fpo])
09 006fe8b4 58d6c4ae 00000001 222d4b14 00000000 clr!Thread::DoAppropriateWaitWorker+0x1d8 (FPO: [Non-Fpo])
0a 006fe920 58d6c5f7 00000001 222d4b14 00000000 clr!Thread::DoAppropriateWait+0x64 (FPO: [Non-Fpo])
0b 006fe96c 58bd13cc ffffffff 00000001 00000000 clr!CLREventBase::WaitEx+0x121 (FPO: [Non-Fpo])
0c 006fe984 58d57bbb ffffffff 00000001 00000000 clr!CLREventBase::Wait+0x1a (FPO: [3,0,0])
0d 006fea10 58d57cec 009e9a08 ffffffff bb93f1e9 clr!AwareLock::EnterEpilogHelper+0xa8 (FPO: [Non-Fpo])
0e 006fea58 58d57ac5 009e9a08 ffffffff 006feb48 clr!AwareLock::EnterEpilog+0x48 (FPO: [Non-Fpo])
0f 006fea70 58ca97d2 bb93f0ad 006feb48 2d87a548 clr!AwareLock::Enter+0x4a (FPO: [0,1,0])
10 006feb1c 14550bb2 179f3680 17a052a0 179f3640 clr!JITutil_MonReliableEnter+0xb5 (FPO: [Non-Fpo])
```

为什么会一直等待一个事件句柄呢，这需要细看这个句柄是哪里来的。仔细观察栈帧的参数部分，可看到句柄数组最后出现在栈帧10，也就是说CLREventBase::WaitEx提供了等待事件的句柄给Thread::DoAppropriateWait函数。那打开IDA，开始解析clr模块，观察CLREventBase::WaitEx函数：

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/VS_deadlock_analysis/58BF08C3-B31E-480e-99ED-51452C9FC063.png)

可看到v7变量是this指针，this变量是CLREventBase实例，而this变量就是等待的数组地址，由此可知CLREventBase是一个没有虚表的类，第一个成员就是等待事件的句柄。

接下来要看CLREventBase实例是在哪生成的，观察栈，在IDA寻找，如下：

![image-20240130145952115](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/VS_deadlock_analysis/image-20240130145952115.png)

![image-20240130150212590](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/VS_deadlock_analysis/image-20240130150212590.png)

可看到CLREventBase实例其实是AwareLock类的一个成员，从Wait的调用往上，可看到AwareLock::AllocLockSemEvent函数，该函数会调用CLREventBase::CreateMonitorEvent，然后CreateMonitorEvent方法会调用CreateEventW(0, 0, 0, 0)来创建事件，这个事件就是0-2栈帧等待的事件句柄。观察到AllocLockSemEvent函数的调用有一个条件：

```cpp
if ( (*((_DWORD *)this + 6) & 8) == 0 )
    AwareLock::AllocLockSemEvent(this);
```

如果this+6*4 地址处的成员变量的第4位不为0，则认为不需要创建事件句柄，这里可理解为第4位不为0，则事件句柄就是存在的，和单例模式的实例创建类似，如果没有才创建。继续往上回溯，看AwareLock的实例是怎么来的：

![image-20240130151048057](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/VS_deadlock_analysis/image-20240130151048057.png)

这是16号栈帧，最后一个有用的栈帧，从代码可看出AwareLock的实例是从ObjHeader::GetSyncBlock来的，google一下该函数，发现这个函数是获取对象的同步块。那这个对象是什么时候，从哪创建的呢？

分析到这里，线索断了。

## .NET程序调试

其实，我们之前是在调试非托管代码，而.NET程序存在文件中的元数据包含的是托管代码，托管代码通过jit化，转成机器码并执行。

只分析非托管代码，能获取的信息是有限的，因此最后还是需要分析托管代码，.NET框架提供了一个sos扩展，该扩展可方便windbg观察托管代码的数据，比如栈、函数的变量和参数等。

因为对sos扩展的使用不熟，所以之前尝试了非托管代码的分析，目前看来走不通了，那就从整体.NET程序的流程来分析。

### 加载sos.dll

为使用sos模块，需要显式在windbg中加载sos模块，加载的方法有两种：

- .load <sos_dll_path>

- .loadby sos <some_module_path>

  > 这里的some_module_path是和sos在同一个目录的模块，且已经被加载到进程里了。

> 关于sos模块的基本使用方法可参考微软的[这篇官方文档](https://learn.microsoft.com/en-us/dotnet/framework/tools/sos-dll-sos-debugging-extension)。

### 从托管代码的角度观察栈

```cpp
0:000> .loadby sos clrjit
0:000> !sos.help
The call to LoadLibrary(sos) failed, Win32 error 0n2 "系统找不到指定的文件。"
0:000> !CLRStack
OS Thread Id: 0x5734 (0)
Child SP       IP Call Site
006fe9ac 7585586c [GCFrame: 006fe9ac] 
006fea8c 7585586c [GCFrame: 006fea8c] 
...
0:000> !sos.help
-------------------------------------------------------------------------------
SOS is a debugger extension DLL designed to aid in the debugging of managed
programs. Functions are listed by category, then roughly in order of
importance. Shortcut names for popular functions are listed in parenthesis.
Type "!help <functionname>" for detailed info on that function. 

Object Inspection                  Examining code and stacks
-----------------------------      -----------------------------
DumpObj (do)                       Threads
...
```

 从以上命令可看到，有时即使执行了.load和.loadby命令，帮助文档还是打不开，但使用了sos的其中一个命令后，就可以打开帮助文档了。

关于sos有哪些命令，可在微软的官方了解，也可以用!sos.help来了解，如果要了解某一条具体的命令，可以输`!help sos_command`：

```cpp
0:000> !help CLRStack
-------------------------------------------------------------------------------
!CLRStack [-a] [-l] [-p] [-n]
!CLRStack [-a] [-l] [-p] [-i] [variable name] [frame]

CLRStack attempts to provide a true stack trace for managed code only. It is
handy for clean, simple traces when debugging straightforward managed 
programs.
```

了解了sos的基本资料后，我们观察下完整的主线程的栈：

```cpp
0:000> !CLRStack
OS Thread Id: 0x5734 (0)
Child SP       IP Call Site
006fe9ac 7585586c [GCFrame: 006fe9ac] 
006fea8c 7585586c [GCFrame: 006fea8c] 
006feaa8 7585586c [HelperMethodFrame_1OBJ: 006feaa8] System.Threading.Monitor.ReliableEnter(System.Object, Boolean ByRef)
006feb24 14550bb2 Microsoft.CodeAnalysis.Options.GlobalOptionService.RefreshOption(Microsoft.CodeAnalysis.Options.OptionKey, System.Object)
006feb64 145508d8 Microsoft.VisualStudio.LanguageServices.Implementation.Options.LanguageSettingsPersister.RefreshLanguageSettings(Microsoft.VisualStudio.TextManager.Interop.LANGPREFERENCES3[])
006febb0 1452a5f1 Microsoft.VisualStudio.LanguageServices.Implementation.Options.LanguageSettingsPersister..ctor(Microsoft.CodeAnalysis.Editor.Shared.Utilities.IThreadingContext, Microsoft.VisualStudio.TextManager.Interop.IVsTextManager4, Microsoft.CodeAnalysis.Options.IGlobalOptionService)
006fecbc 14529755 Microsoft.VisualStudio.LanguageServices.Implementation.Options.LanguageSettingsPersisterProvider+d__5.MoveNext()
006fed30 55abcc3a System.Runtime.CompilerServices.AsyncMethodBuilderCore+MoveNextRunner.InvokeMoveNext(System.Object)
006fed38 55a53674 System.Threading.ExecutionContext.RunInternal(System.Threading.ExecutionContext, System.Threading.ContextCallback, System.Object, Boolean)
006feda4 55a535a7 System.Threading.ExecutionContext.Run(System.Threading.ExecutionContext, System.Threading.ContextCallback, System.Object, Boolean)
006fedb8 55abcb8e System.Runtime.CompilerServices.AsyncMethodBuilderCore+MoveNextRunner.Run()
006fede8 51b0e8fd Microsoft.VisualStudio.Threading.JoinableTaskFactory+SingleExecuteProtector.TryExecute()
006fee2c 51ac0c4a Microsoft.VisualStudio.Threading.JoinableTaskFactory+SingleExecuteProtector+c.b__20_0(System.Object)
006fee30 5449efae System.Windows.Threading.ExceptionWrapper.InternalRealCall(System.Delegate, System.Object, Int32)
006fee50 5449ee95 System.Windows.Threading.ExceptionWrapper.TryCatchWhen(System.Object, System.Delegate, System.Object, Int32, System.Delegate)
006fee94 544a11cd System.Windows.Threading.DispatcherOperation.InvokeImpl()
006feecc 5449f67f System.Windows.Threading.DispatcherOperation.InvokeInSecurityContext(System.Object)
006feed4 544a0f9b System.Windows.Threading.DispatcherOperation.Invoke()
006fef08 5449d456 System.Windows.Threading.Dispatcher.ProcessQueue()
006fef48 5449c57c System.Windows.Threading.Dispatcher.WndProcHook(IntPtr, Int32, IntPtr, IntPtr, Boolean ByRef)
006fef94 5449e771 MS.Win32.HwndWrapper.WndProc(IntPtr, Int32, IntPtr, IntPtr, Boolean ByRef)
006fefd0 5449ea5c MS.Win32.HwndSubclass.DispatcherCallbackOperation(System.Object)
006fefe0 5449ef52 System.Windows.Threading.ExceptionWrapper.InternalRealCall(System.Delegate, System.Object, Int32)
006ff000 5449ee95 System.Windows.Threading.ExceptionWrapper.TryCatchWhen(System.Object, System.Delegate, System.Object, Int32, System.Delegate)
006ff044 5449d072 System.Windows.Threading.Dispatcher.LegacyInvokeImpl(System.Windows.Threading.DispatcherPriority, System.TimeSpan, System.Delegate, System.Object, Int32)
006ff0a0 5449e5c4 MS.Win32.HwndSubclass.SubclassWndProc(IntPtr, Int32, IntPtr, IntPtr)
```

首先GCFrame是保护对象引用的，其实不是方法调用，如下：

```cpp
//------------------------------------------------------------------------
// This frame protects object references for the EE's convenience.
// This frame type actually is created from C++.
//------------------------------------------------------------------------
class GCFrame : public Frame {/*...*/}
```

往下看，可以看到Microsoft.CodeAnalysis.Options.GlobalOptionService.RefreshOption是调用等待的函数，这个函数是C#语言的函数，我们可以找到该函数所处模块，然后用dnSpy反编译代码查看对应的代码。为找到该函数对应的模块，首先使用`!CLTStack -a`命令打印所有栈帧：

> 因为某些原因，我重启了VS，以下偏移会不太一样，不过不影响分析流程的理解。

![image-20240130170349796](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/VS_deadlock_analysis/image-20240130170349796.png)

Microsoft.CodeAnalysis.Options.GlobalOptionService的类实例是0x3a4d75b4，点击这个地址，会执行命令`!DumpObj /d 3a4d75b4`，该命令结果如下：

```cpp
0:000> !DumpObj /d 3a4d75b4
Name:        Microsoft.CodeAnalysis.Options.GlobalOptionService
MethodTable: 17196770
EEClass:     127da2a4
Size:        64(0x40) bytes
File:        c:\program files (x86)\microsoft visual studio\2019\community\common7\ide\commonextensions\microsoft\managedlanguages\vbcsharp\languageservices\Microsoft.CodeAnalysis.Workspaces.dll
Fields:
      MT    Field   Offset                 Type VT     Attr    Value Name
17195bc4  4000669        4 ...eThreadingService  0 instance 3a4b4788 _workspaceThreadingService
00000000  400066a        8                       0 instance 3a4d7898 _lazyAllOptions
...
```

其中有一个File字段，这个字段对应的RefreshOption方法的所在模块。

题外话，DumpObj的结果还有一个MethodTable字段，点击地址，会执行`!DumpMT /d 17196770`命令，输出这个类的方法统计信息。由于这样无法打印该类的所有方法，所以我们通过执行`!help DumpMT`命令，可以查看其具体用法，如下：

```
0:000> !help DumpMT
-------------------------------------------------------------------------------
!DumpMT [-MD] <MethodTable address>

Examine a MethodTable. Each managed object has a MethodTable pointer at the 
start. If you pass the "-MD" flag, you'll also see a list of all the methods 
defined on the object.
```

所以，最终执行`!DumpMT /d -MD 17196770`命令可查看该类的所有方法，如下：

```cpp
0:000> !DumpMT /d -MD 17196770
EEClass:         127da2a4
Module:          2a5533d8
Name:            Microsoft.CodeAnalysis.Options.GlobalOptionService
mdToken:         0200027e
File:            c:\program files (x86)\microsoft visual studio\2019\community\common7\ide\commonextensions\microsoft\managedlanguages\vbcsharp\languageservices\Microsoft.CodeAnalysis.Workspaces.dll
BaseSize:        0x40
ComponentSize:   0x0
Slots in VTable: 33
Number of IFaces in IFaceMap: 1
--------------------------------------
MethodDesc Table
   Entry MethodDe    JIT Name
55a64838 5565c838 PreJIT System.Object.ToString()
55a64720 5579a7a0 PreJIT System.Object.Equals(System.Object)
55a6d270 5579a7c0 PreJIT System.Object.GetHashCode()
55a1ff2c 5579a7c8 PreJIT System.Object.Finalize()
0708f6b9 17196630   NONE Microsoft.CodeAnalysis.Options.GlobalOptionService.GetRegisteredOptions()
1e8a8210 171966d4    JIT Microsoft.CodeAnalysis.Options.GlobalOptionService.RefreshOption(Microsoft.CodeAnalysis.Options.OptionKey, System.Object)
171a3c90 171966e8    JIT Microsoft.CodeAnalysis.Options.GlobalOptionService.RegisterWorkspace(Microsoft.CodeAnalysis.Workspace)
0708f6f9 171966f0   NONE Microsoft.CodeAnalysis.Options.GlobalOptionService.UnregisterWorkspace(Microsoft.CodeAnalysis.Workspace)
171a3c00 171966f8    JIT Microsoft.CodeAnalysis.Options.GlobalOptionService.add_OptionChanged(System.EventHandler`1)
0708f701 17196700   NONE Microsoft.CodeAnalysis.Options.GlobalOptionService.remove_OptionChanged(System.EventHandler`1)
0708fc28 17196708    JIT Microsoft.CodeAnalysis.Options.GlobalOptionService..cctor()
...
```

紧接正文，找到模块后，用dnSpy打开，查看如下代码：

```csharp
// Microsoft.CodeAnalysis.Options.GlobalOptionService
// Token: 0x06001E97 RID: 7831 RVA: 0x00065854 File Offset: 0x00063A54
[NullableContext(2)]
public bool RefreshOption(OptionKey2 optionKey, object newValue)
{
	object gate = this._gate;
	lock (gate)
	{
		object objA;
		if (this._currentValues.TryGetValue(optionKey, out objA) && object.Equals(objA, newValue))
		{
			return false;
		}
		this._currentValues = this._currentValues.SetItem(optionKey, newValue);
	}
	List<OptionChangedEventArgs> changedOptions = new List<OptionChangedEventArgs>
	{
		new OptionChangedEventArgs(optionKey, newValue)
	};
	this.RaiseOptionChangedEvent(changedOptions);
	return true;
}
```

根据我们在非托管代码的分析，当时的等待事件句柄应该就是这个this.\_gate对象里的事件句柄了。从代码中可了解到，应该是其他线程锁住了\_gate这个对象，导致主线程一直等待，然后锁住\_gate的线程又因为什么原因，一直在等待，所以导致了死锁。那么锁住\_gate的线程是谁呢？这时就需要打印所有线程的栈了。

### 观察所有线程的栈

运行命令`~*e !CLRStack`，打印所有线程的栈，其中发现一个与GlobalOptionService类有关的线程，其栈如下：

> 注：在'~*'后面要跟一个'e'，这样才能对所有线程执行扩展命令。

```cpp
OS Thread Id: 0x1d30 (11)
Child SP       IP Call Site
GetFrameContext failed: 1
00000000 00000000 
OS Thread Id: 0x65a0 (12)
Child SP       IP Call Site
066cede8 7717315c [GCFrame: 066cede8] 
066cee98 7717315c [HelperMethodFrame_1OBJ: 066cee98] System.Threading.Monitor.ObjWait(Boolean, Int32, System.Object)
066cef24 55a2f348 System.Threading.Monitor.Wait(System.Object, Int32, Boolean)
066cef34 55a3d46d System.Threading.Monitor.Wait(System.Object, Int32)
066cef38 55aba689 System.Threading.ManualResetEventSlim.Wait(Int32, System.Threading.CancellationToken)
066cef8c 55ab8a29 System.Threading.Tasks.Task.SpinThenBlockingWait(Int32, System.Threading.CancellationToken)
066cefcc 55b1b4f9 System.Threading.Tasks.Task.InternalWait(Int32, System.Threading.CancellationToken)
066cf030 55ab8896 System.Threading.Tasks.Task.Wait(Int32, System.Threading.CancellationToken)
066cf040 55ab884d System.Threading.Tasks.Task.Wait(System.TimeSpan)
066cf058 51b10529 Microsoft.VisualStudio.Threading.JoinableTaskFactory.WaitSynchronouslyCore(System.Threading.Tasks.Task)
066cf0cc 51b104a7 Microsoft.VisualStudio.Threading.JoinableTaskFactory.WaitSynchronously(System.Threading.Tasks.Task)
066cf110 51b0c176 Microsoft.VisualStudio.Threading.JoinableTask.CompleteOnCurrentThread()
066cf17c 1e8a0eb3 Microsoft.VisualStudio.Threading.JoinableTask`1[[System.Collections.Immutable.ImmutableArray`1[[System.__Canon, mscorlib]], System.Collections.Immutable]].CompleteOnCurrentThread()
066cf18c 1e7cc435 Microsoft.VisualStudio.Threading.JoinableTaskFactory.Run[[System.Collections.Immutable.ImmutableArray`1[[System.__Canon, mscorlib]], System.Collections.Immutable]](System.Func`1>>, Microsoft.VisualStudio.Threading.JoinableTaskCreationOptions)
066cf1ac 1e7cc3d0 Microsoft.VisualStudio.Threading.JoinableTaskFactory.Run[[System.Collections.Immutable.ImmutableArray`1[[System.__Canon, mscorlib]], System.Collections.Immutable]](System.Func`1>>)
066cf1c4 1e7cc37d Microsoft.CodeAnalysis.Editor.Shared.Utilities.WorkspaceThreadingService.Run[[System.Collections.Immutable.ImmutableArray`1[[System.__Canon, mscorlib]], System.Collections.Immutable]](System.Func`1>>) [/_/src/EditorFeatures/Core/Shared/Utilities/WorkspaceThreadingService.cs @ 28]
066cf1e0 1e7cc2f5 Microsoft.CodeAnalysis.Options.GlobalOptionService.g__GetOptionPersistersSlow|16_0(Microsoft.CodeAnalysis.Shared.Utilities.IWorkspaceThreadingService, System.Collections.Immutable.ImmutableArray`1>, System.Threading.CancellationToken) [/_/src/Workspaces/Core/Portable/Options/GlobalOptionService.cs @ 128]
066cf1fc 1e7cc25b Microsoft.CodeAnalysis.Options.GlobalOptionService.GetOptionPersisters() [/_/src/Workspaces/Core/Portable/Options/GlobalOptionService.cs @ 114]
066cf214 1e7cc1ae Microsoft.CodeAnalysis.Options.GlobalOptionService.LoadOptionFromSerializerOrGetDefault(Microsoft.CodeAnalysis.Options.OptionKey) [/_/src/Workspaces/Core/Portable/Options/GlobalOptionService.cs @ 144]
066cf234 1e7cbdd1 Microsoft.CodeAnalysis.Options.GlobalOptionService.GetOption_NoLock(Microsoft.CodeAnalysis.Options.OptionKey) [/_/src/Workspaces/Core/Portable/Options/GlobalOptionService.cs @ 345]
066cf250 1e7cbd3b Microsoft.CodeAnalysis.Options.GlobalOptionService.GetOption(Microsoft.CodeAnalysis.Options.OptionKey)
066cf288 1e7cbc75 Microsoft.CodeAnalysis.Options.OptionsHelpers.GetOption[[System.Boolean, mscorlib]](Microsoft.CodeAnalysis.Options.OptionKey, System.Func`2) [/_/src/Workspaces/Core/Portable/Options/OptionsHelpers.cs @ 29]
066cf2a0 1e7cbaeb Microsoft.CodeAnalysis.Options.GlobalOptionService.GetOption[[System.Boolean, mscorlib]](Microsoft.CodeAnalysis.Options.Option2`1) [/_/src/Workspaces/Core/Portable/Options/GlobalOptionService.cs @ 312]
066cf2bc 1e7cb669 Microsoft.CodeAnalysis.Options.OptionServiceFactory+OptionService.GetOption[[System.Boolean, mscorlib]](Microsoft.CodeAnalysis.Options.Option2`1) [/_/src/Workspaces/Core/Portable/Options/OptionServiceFactory.cs @ 120]
066cf2cc 1e7caf45 Microsoft.CodeAnalysis.Remote.RemoteHostOptions.IsUsingServiceHubOutOfProcess(Microsoft.CodeAnalysis.Host.HostWorkspaceServices) [/_/src/Workspaces/Remote/Core/RemoteHostOptions.cs @ 69]
...
```

该线程也在等待，其中GlobalOptionService的最后一个调用是GlobalOptionService.g__GetOptionPersistersSlow|16_0，观察源代码:

```csharp
internal static ImmutableArray<IOptionPersister> <GetOptionPersisters>g__GetOptionPersistersSlow|16_0(IWorkspaceThreadingService workspaceThreadingService, [Nullable(new byte[]{0,1,1})] ImmutableArray<Lazy<IOptionPersisterProvider>> optionSerializerProviders, CancellationToken cancellationToken) {
		if (workspaceThreadingService != null)
		{
			return workspaceThreadingService.Run<ImmutableArray<IOptionPersister>>(() => GlobalOptionService.<GetOptionPersisters>g__GetOptionPersistersAsync|16_1(optionSerializerProviders, cancellationToken));
		}
		return GlobalOptionService.<GetOptionPersisters>g__GetOptionPersistersAsync|16_1(optionSerializerProviders, cancellationToken).WaitAndGetResult_CanCallOnBackground(cancellationToken);
```

因为该函数是最后一个函数，即workspaceThreadingService不为null。从栈来看，调用workspaceThreadingService.Run方法后，就调用Microsoft.VisualStudio.Threading.JoinableTask.CompleteOnCurrentThread()，做同步等待，即等待异步的g__GetOptionPersistersAsync|16_1函数执行完成。

g__GetOptionPersistersAsync|16_1方法如下：

```csharp
internal static Task<ImmutableArray<IOptionPersister>> <GetOptionPersisters>g__GetOptionPersistersAsync|16_1([Nullable(new byte[]{0,1,1})] ImmutableArray<Lazy<IOptionPersisterProvider>> optionSerializerProviders, CancellationToken cancellationToken)
{
    GlobalOptionService.<<GetOptionPersisters>g__GetOptionPersistersAsync|16_1>d <<GetOptionPersisters>g__GetOptionPersistersAsync|16_1>d;
    <<GetOptionPersisters>g__GetOptionPersistersAsync|16_1>d.<>t__builder = AsyncTaskMethodBuilder<ImmutableArray<IOptionPersister>>.Create();
    <<GetOptionPersisters>g__GetOptionPersistersAsync|16_1>d.optionSerializerProviders = optionSerializerProviders;
    <<GetOptionPersisters>g__GetOptionPersistersAsync|16_1>d.cancellationToken = cancellationToken;
    <<GetOptionPersisters>g__GetOptionPersistersAsync|16_1>d.<>1__state = -1;
    <<GetOptionPersisters>g__GetOptionPersistersAsync|16_1>d.<>t__builder.Start<GlobalOptionService.<<GetOptionPersisters>g__GetOptionPersistersAsync|16_1>d>(ref <<GetOptionPersisters>g__GetOptionPersistersAsync|16_1>d);
    return <<GetOptionPersisters>g__GetOptionPersistersAsync|16_1>d.<>t__builder.Task;
}
```

\<\<GetOptionPersisters>g__GetOptionPersistersAsync|16_1>d 是编译器生成的类，应该属于lambda、闭包那一类。该类实现了IAsyncStateMachine接口，该接口有一个MoveNext方法，在该类的实现如下：

```csharp
void IAsyncStateMachine.MoveNext() {
    int num = this.<>1__state;
    ImmutableArray<IOptionPersister> result;
    try
    {
        ConfiguredValueTaskAwaitable<ImmutableArray<IOptionPersister>>.ConfiguredValueTaskAwaiter awaiter;
        if (num != 0)
        {
            awaiter = this.optionSerializerProviders.SelectAsArrayAsync(new Func<Lazy<IOptionPersisterProvider>, CancellationToken, ValueTask<IOptionPersister>>(GlobalOptionService.<>c.<>9.<GetOptionPersisters>b__16_3), this.cancellationToken).ConfigureAwait(false).GetAwaiter();
//以下省略...
```

调用SelectAsArrayAsync函数，该函数接收一个参数\<GetOptionPersisters\>b__16_3，这个参数是一个函数，该函数实现如下：

```csharp
internal ValueTask<IOptionPersister> <GetOptionPersisters>b__16_3(Lazy<IOptionPersisterProvider> lazyProvider, CancellationToken cancellationToken)
			{
				return lazyProvider.Value.GetOrCreatePersisterAsync(cancellationToken);
			}
```

GetOrCreatePersisterAsync函数是IOptionPersisterProvider接口的一个函数，该函数会在另一个线程执行。再往回看主线程的栈

```cpp
010ff074 1e8a110d Microsoft.VisualStudio.LanguageServices.Implementation.Options.LanguageSettingsPersisterProvider+d__5.MoveNext() [/_/src/VisualStudio/Core/Def/Implementation/Options/LanguageSettingsPersisterProvider.cs @ 50]
010ff0e8 55abcc3a System.Runtime.CompilerServices.AsyncMethodBuilderCore+MoveNextRunner.InvokeMoveNext(System.Object)
```

最底下是异步调用，然后异步调用会调用LanguageSettingsPersisterProvider类的相关函数，执行`!CLRStack -a`命令，找到这个类对应的模块名为

Microsoft.VisualStudio.LanguageServices.dll，用dnSpy打开，定位到该类，发现恰好有GetOrCreatePersisterAsync函数：

![image-20240131095542869](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/VS_deadlock_analysis/image-20240131095542869.png)

也就是说IOptionPersisterProvider接口的实现类是LanguageSettingsPersisterProvider，该函数负责执行状态机类\<GetOrCreatePersisterAsync\>d\_\_5，也就是主线程栈上的LanguageSettingsPersisterProvider+d__5类的MoveNext函数。MoveNext函数会新建一个LanguageSettingsPersister实例：

![image-20240131101620825](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/VS_deadlock_analysis/image-20240131101620825.png)

该构造函数会初始化一个map，描述语言配置，比如C#、F#，如果\_textManager.GetUserPreferences4能获取到对应语言的配置，那么就调用RefreshLanguageSettings，进一步调用RefreshOption更新选项配置：

![image-20240131101914130](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/VS_deadlock_analysis/image-20240131101914130.png)

这与主线程的栈是一致的。到这里梳理一下流程：

![image-20240131113710274](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/VS_deadlock_analysis/image-20240131113710274.png)

红圈中两个线程相互等待，导致死锁。

## VS卡死的原因

根据调试分析，发现如果有对应的语言配置，就会去更新选项配置。回想起不久前，我安装了C#的开发环境，可能是因为这样，导致VS能找到C#的语言配置，所以走入了新流程，即更新选项配置，但这时由于另一个线程锁住了_gate，所以这就导致主线程的等待。

## 解决问题

既然大概有眉目了，那第一种方法就是卸载C#的开发环境。不过这不是长久之计，还是需要更优雅的方法。google之后，我发现roslyn开源库里正好提到了这个问题，有一个open的[issue](https://github.com/dotnet/roslyn/issues/34283)，并且开发者在高版本还修复了这个问题，merge是[这个](https://github.com/dotnet/roslyn/pull/54845)，关键代码如下：

```csharp
//之前：
public object GetOption(OptionKey optionKey)
{
	object gate = this._gate;
	object option_NoLock;
	lock (gate)
	{
		option_NoLock = this.GetOption_NoLock(optionKey);
	}
	return option_NoLock;
}

//之后
public object GetOption(OptionKey optionKey)
{
    // Ensure the option persisters are available before taking the global lock
    var persisters = GetOptionPersisters();
    
	object gate = this._gate;
	object option_NoLock;
	lock (gate)
	{
		option_NoLock = this.GetOption_NoLock(optionKey, persisters);
	}
	return option_NoLock;
}
```

这里persister类实例的构建放在了gate对象锁的外面，这样就不会导致主线程无限等待了。

也就是说更新对应Microsoft.CodeAnalysis.workspaces.dll的版本就行了，我尝试更新了.NET的运行时，似乎都没更新这个dll，最后我下载了VS的扩展开发组件，该组件包含了roslyn的对应dll，替换dll后问题解决。

![image-20240131115945607](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/VS_deadlock_analysis/image-20240131115945607.png)
