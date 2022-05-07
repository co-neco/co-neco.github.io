---
title: 记一次win10下程序以兼容方式启动导致的死锁
categories:
  - Technology
  - Development
date: 2021-10-25 19:42:40
tags:
  - deadlock
---

## 起因

某一天开发完做测试的时候，发现测试程序没有输出日志。确定与新功能没关系后，决定上windbg一探究竟，最后定位的结果是垫片引擎和ntdll模块的锁之间形成了死锁关系。

接下来记录一下死锁的形成经历。

## 观察主线程状态

```c
 # ChildEBP RetAddr  Args to Child              
00 008fe8e0 775f57da 6be0c9ac 00000000 02c78f58 ntdll!NtWaitForAlertByThreadId+0xc (FPO: [2,0,0])
01 008fe944 6bdddaa3 6be0c9ac 00000000 02c78f28 ntdll!RtlAcquireSRWLockShared+0x1ca (FPO: [1,17,4])
02 008fe980 6bddd0b3 00000000 00000000 00000009 AcLayers!NS_FaultTolerantHeap::FthDelayFreeQueueInsert+0x7b (FPO: [1,9,4])
03 008feabc 74e9be65 00d30000 00140009 02c78f28 AcLayers!NS_FaultTolerantHeap::APIHook_RtlReAllocateHeap+0x843 (FPO: [Non-Fpo])
04 008feb14 77455486 KERNELBASE!LocalReAlloc+0x135
05 008feb74 77476827 MSCTF!CCategoryMgr::s_RegisterGUID+0x286
...
0a 008fec7c 762c38dc MSCTF!CtfImeCreateInputContext+0x30
...
0e 008fed1c 764e0f92 IMM32!ImmSetActiveContext+0x34f
...
15 008ff154 764ee4cf USER32!DispatchClientMessage+0xea
16 008ff190 7763537d USER32!__fnDWORD+0x3f
17 008ff1c8 764a30ac ntdll!KiUserCallbackDispatcher+0x4d
18 008ff1cc 76540ad9 win32u!NtUserSetFocus+0xc
...
26 008ff8ec 009c9d6d USER32!MessageBoxW+0x45
WARNING: Stack unwind information not available. Following frames may be wrong.
27 008ffab8 00a1157e xx_tester+0xa9d6d
...
2c 008ffb48 77628944 KERNEL32!BaseThreadInitThunk+0x19
2d 008ffba4 77628914 ntdll!__RtlUserThreadStart+0x2f
2e 008ffbb4 00000000 ntdll!_RtlUserThreadStart+0x1b
```

观察windbg打印的栈，可看出主线程调用MessageBox就没有返回了。

> 注：调用MessageBox之前，xx_tester创建了一个线程，用于关掉该消息框。不过主线程还没有创建好消息框就卡住了。另外，主线程弹出消息框只是用于测试windows的全局钩子，所以请大家不要模仿。

看02~03的调用，通过LocalReAlloc进入了AcLayers模块的堆管理部分。AcLayers是windows在winXP引入的垫片机制的一个垫片（apphelp.dll是垫片引擎）。为了兼容可能出现的堆错误，这里使用了AcLayers垫片的容错堆功能。

> 注：堆有一些调试支持，比如堆尾检查（Heap Tail Check/HTC）、释放检查（Heap Free Check/HFC）等，和FTH名字很像，不过FTH是一个自win7以来提供的子系统，用于监控应用程序的崩溃，并在之后的启动中，提供缓解方法来避免崩溃。

看00~01的调用，发现AcLayers调用了ntdll的RtlAcquireSRWLockShared，这个函数是在等一个SRWLock，然后就一去不复返了。windbg没有srwlock相关的扩展命令，不过可以通过_RTL_SRWLOCK来观察结构体的内容，如下：

```c
0:000> dt ntdll!_RTL_SRWLOCK 6be0c9ac 
   +0x000 Locked           : 0y1
   +0x000 Waiting          : 0y1
   +0x000 Waking           : 0y0
   +0x000 MultipleShared   : 0y0
   +0x000 Shared           : 0y0000000010001111111010010010 (0x8fe92)
   +0x000 Value            : 0x8fe923
   +0x000 Ptr              : 0x008fe923 Void
```

从这个结构体的内容可看出，另外一个线程持有这个锁。因为SRWLock是微软内部使用的，没有公开文档，所以从该结构体，我们暂且还不知是哪个线程持有这个锁。

> 注：SRWLock不能看出谁持有锁，但CRITICAL_SECTION可以看出。

## windbg的附加线程

用windbg附加的时候，发现无法立刻中断下来，弹出如下内容：

```c
Break-in sent, waiting 30 seconds...
WARNING: Break-in timed out, suspending.
         This is usually caused by another thread holding the loader lock
(5874.4b38): Wake debugger - code 80000007 (first chance)
eax=00004b38 ebx=6be0c9ac ecx=00000000 edx=00000000 esi=00000001 edi=6be0c9ac
eip=77634bbc esp=008fe8e4 ebp=008fe944 iopl=0         nv up ei pl nz na pe nc
cs=0023  ss=002b  ds=002b  es=002b  fs=0053  gs=002b             efl=00000206
ntdll!NtWaitForAlertByThreadId+0xc:
77634bbc c20800          ret     8
```

因为windbg附加时，是通过远线程的方式调用被调试进程的DbgUiRemoteBreakin函数，那为何附加线程无法中断呢？观察这个线程的栈如下：

```c
0:013> kv
 # ChildEBP RetAddr 
00 097ef0e8 7761b79b 7b55f2a4 00000000 7b55f2a0 ntdll!NtWaitForAlertByThreadId+0xc (FPO: [2,0,0])
01 097ef120 7761b46d 00000000 00000000 7b55f2a4 ntdll!RtlpWaitOnAddressWithTimeout+0xc0 (FPO: [Non-Fpo])
02 097ef1c0 7760d681 097ef3a0 097efa48 00000000 ntdll!RtlpWaitOnCriticalSection+0x18d (FPO: [Non-Fpo])
03 097ef1f8 7760ae09 097ef20c 7b328b95 7b55f2a0 ntdll!RtlpEnterCriticalSectionContended+0x261 (FPO: [Non-Fpo])
04 097ef200 7b328b95 7b55f2a0 097ef264 7b2e17f3 ntdll!RtlEnterCriticalSection+0x49 (FPO: [1,0,0])
05 097ef20c 7b2e17f3 xx!__acrt_lock+0x15
06 097ef264 7b2e1746 xx!heap_alloc_dbg_internal+0x43
07 097ef288 7b2e476a xx!heap_alloc_dbg+0x36
08 097ef2a0 7b323124 xx!_malloc_dbg+0x1a
09 097ef2b8 7b0a672d xx!malloc+0x14
...
13 097efb20 775f2ee9 xx!NtContinueDetour+0x46
14 097efb34 00000000 ntdll!LdrInitializeThunk+0x29
```

观察13~14的调用，发现在切换到DbgUiRemoteBreakin之前，就已经卡住了。

> 注：当创建新的线程时，都会先调用LdrInitializeThunk，做一些线程的初始化，然后调用NtContinue函数。NtContinue会将CONTEXT结构体的eip设置为线程真正的起始执行入口。

观察05~09的调用，在测试时，我对NtContinue做了inlinehook，NtContinueDetour就是inlinehook的中间函数。NtContinueDetour在检查的途中，分配了堆块，最后调用了微软的C运行时库函数_\_acrt_lock。

观察04的调用，发现附加线程卡住的原因是在等待一个CRITICAL_SECTION，观察这个锁：

```c
0:013> !cs 7b55f2a0 
-----------------------------------------
Critical section   = 0x7b55f2a0 (JJDPS!__acrt_lock_table+0x0)
DebugInfo          = 0x00d6b4b8
LOCKED
LockCount          = 0x3
WaiterWoken        = No
OwningThread       = 0x000047b8
RecursionCount     = 0x1
LockSemaphore      = 0xFFFFFFFF
SpinCount          = 0x00000fa0
```

OwningThread指明了线程ID为0x000047b8的线程持有这个锁，那我们切换到这个线程，观察它的栈：

```c
0:007> kv
# ChildEBP RetAddr  Args to Child  
00 096ee580 7761b79b 00d3025c 00000000 00d30258 ntdll!NtWaitForAlertByThreadId+0xc (FPO: [2,0,0])
01 096ee5b8 7761b46d 00000000 00000000 00d3025c ntdll!RtlpWaitOnAddressWithTimeout+0xc0 (FPO: [Non-Fpo])
02 096ee658 7760d681 00000000 00d30000 00000000 ntdll!RtlpWaitOnCriticalSection+0x18d (FPO: [Non-Fpo])
03 096ee690 7760ae09 00000000 096ee6fc 776a9b5c ntdll!RtlpEnterCriticalSectionContended+0x261 (FPO: [Non-Fpo])
04 096ee69c 776a9b5c 00d30258 46b3037b 00d30000 ntdll!RtlEnterCriticalSection+0x49 (FPO: [1,0,0])
05 096ee6fc 7760d8c6 ntdll!RtlDebugFreeHeap+0x87
06 096ee858 77647e9b ntdll!RtlpFreeHeap+0xd6
07 096ee8b4 7760d796 ntdll!RtlpFreeHeapInternal+0x783
08 096ee8d4 6bddd9d4 ntdll!RtlFreeHeap+0x46
09 096ee90c 6bddea9a AcLayers!NS_FaultTolerantHeap::FthDelayFreeQueueFlush+0x125
0a 096ee91c 6bddd1a3 AcLayers!NS_FaultTolerantHeap::FthValidateHeap+0x55
0b 096ee928 74eccbf4 AcLayers!NS_FaultTolerantHeap::APIHook_RtlValidateHeap+0x13
0c 096ee93c 7b2e2e4b KERNELBASE!HeapValidate+0x14
0d 096ee950 7b2e11de xx!_CrtIsValidHeapPointer+0x2b 
0e 096ee968 7b2e46ec xx!free_dbg_nolock+0xce 
0f 096ee9a8 7b0a7d1e xx!_free_dbg+0x7c 
10 096ee9b8 7b0a678c xx!operator delete+0xe 
11 096ee9c4 7af6223e xx!operator delete+0xc
...
17 096eef4c 7af5fe72 xx!std::shared_ptr
18 096ef03c 7af67c35 xx!nlohmann::detail::serializer
19 096ef4c0 7af62ee6 xx!nlohmann::basic_json
...
20 096efcec 775f869b ntdll!TppTimerpExecuteCallback+0x98
21 096efe9c 76676359 ntdll!TppWorkerThread+0x73b
22 096efeac 77628944 KERNEL32!BaseThreadInitThunk+0x19
23 096eff08 77628914 ntdll!__RtlUserThreadStart+0x2f
24 096eff18 00000000 ntdll!_RtlUserThreadStart+0x1b
```

观察20~24的调用，这是一个线程池里的线程，然后周期性地调用着一个回调。

观察17~19的调用，发现是nlohmann的json类在调用构造函数。

观察05~11的调用，发现也调用了AcLayers垫片的FTH。

观察04的调用，可知7号线程也在等待一个CS锁，观察这个锁如下：

```c
0:007> !cs 00d30258 
-----------------------------------------
Critical section   = 0x00d30258 (+0xD30258)
DebugInfo          = 0x776dc920
LOCKED
LockCount          = 0x3
WaiterWoken        = No
OwningThread       = 0x00004b38
RecursionCount     = 0x1
LockSemaphore      = 0xFFFFFFFF
SpinCount          = 0x020007cf
```

这个cs锁的持有者是线程0x00004b38，这个线程就是主线程。

通过以上的分析，可以猜想是主线程和7号线程发生了死锁，然后其他线程也因执行堆的相关操作而全都卡住。

## 定位死锁的原因

回想主线程等待的SRWLock，通过它的地址，我们可以知道这个锁的具体名字：

```c
ln 6be0c9ac 
Browse module
Set bu breakpoint
(6be0c9ac)   AcLayers!NS_FaultTolerantHeap::FthDelayFreeQueueFlushLock
```

这个SRWLock的名字叫FthDelayFreeQueueFlushLock。在IDA中，我们可以看到AcLayers垫片的FthDelayFreeQueueInsert函数是如何尝试获取SRWLock的：

![image-20211025214331561](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/development/image-20211025214331561.png)

交叉引用FthDelayFreeQueueFlushLock，发现有多个函数会获取这个锁：

![image-20211025214725855](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/development/image-20211025214725855.png)

再观察7号线程，发现7号线程在获取CS锁之前，调用了FthDelayFreeQueueFlush函数，通过IDA观察如下：

![image-20211025220130896](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/development/image-20211025220130896.png)

FthDelayFreeQueueFlush函数做的第一件事就是以独占的方式获取FthDelayFreeQueueFlushLock。

## 结论

主线程获取了CS锁后，因为进入了AcLayers垫片的FTH，所以尝试获取共享的FthDelayFreeQueueFlushLock；

而7号线程在获取了独占的FthDelayFreeQueueFlushLock后，又希望获取主线程持有的CS锁；

其他线程也因为处理堆时，进入了AcLayers垫片，进而尝试获取堆相关的CS锁，导致暂停，最后整个进程都死锁了。

这个问题是win10下，在调试器中启动程序的调试版本+兼容模式出现的，程序正常启动是不会造成此问题的（因为不会启用调试堆）。如果不以兼容模式运行程序，那也不会造成此问题（因为不会启用垫片引擎）。

