---
title: Process_Injection
categories:
  - Technology
  - Reverse
date: 2022-02-14 19:52:13
tags:
  - process injection
  - Windows Internals
---

# 高级进程注入总结

前几天看玄武的“每日安全”板块，发现了一篇关于[进程注入](https://github.com/RedTeamOperations/Advanced-Process-Injection-Workshop)的文章，之前了解过一些相关的技术，不过是零散的。看到文章总结的挺详细的，且各种方法的异同细节容易忘，于是就想着总结一下各种`进程注入`的异同和优缺点，因此有了本文。

> - 关于常见的进程注入方法，请参考[这个](https://www.cnblogs.com/LittleHann/p/6336950.html)和[这个](https://www.elastic.co/cn/blog/ten-process-injection-techniques-technical-survey-common-and-trending-process)，本文将重点描述值得留意的方法（比如Module Stomping），和一些思路新颖的方法。
>- 以下描述的方法在[进程注入](https://github.com/RedTeamOperations/Advanced-Process-Injection-Workshop)这个仓库都能找到。

## 进程注入简介

进程注入就是将代码注入到另一个进程中，shellcode注入和DLL注入都属于进程注入。

进程注入的作用是隐藏自身或者利用另一个进程的权限做一些不好的事情\^_\^，比如病毒等恶意程序注入到一个正常的进程，以此隐藏自己。

进程注入的方法非常之多，很多与DLL注入有关，比如注册表（Image File Execution Options）、DLL劫持、输入法、COM、LSP劫持（LayerService Provider，与winsock有关）...

除了DLL注入，还有shellcode注入，因为shellcode更小，所以shellcode的使用也更加多样。

2017年，在黑客大会上Eugene Kogan和Tal Liberman又分享了更加隐蔽和特别的方法，比如Process Doppelganging。那么接下来就开始进程注入方法的介绍。

## Module Stomping

该方法通过在目标进程中加载一个合法DLL，然后将shellcode或恶意DLL覆写到这个合法DLL的地址空间里。

伪代码如下（省略错误检查）：

```cpp
HANDLE hTargetHandle = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | PROCESS_ALL_ACCESS | PROCESS_SUSPEND_RESUME, FALSE, targetPid);
//...

// Use OpenProcess + VirtualAllocEx + CreateRemoteThread(the traditional dll injection method)
injectLoadLibrary(hTargetHandle, legitimateDll);
//...

// Copy every malware dll's section into legitimate dll's corresponding sections within the target process address space.
for(section : malwareDll){
    WriteProcessMemory(hTargetHandle, legitimateDllSection, section, section_size...);
    
    if (has executable section)
        BypassCFG();
}

RebuildImportTable();
RebuildRelocationTable();

callTLSCallback();

CreateRemoteThread(malwareDllEntryPoint);

```

通过该方法可以将恶意代码隐藏，使得Defender扫描目标进程空间时不会发现恶意代码的存在（因为恶意代码潜伏在合法的模块里）。

该方法有两个值得关注的点：

- 先在目标进程加载一个合法DLL，以此隐藏恶意代码。

- 它用了`SetProcessValidCallTargets`，该方法可以bypass开启CFG的程序。

> 与CFG(control flow guard)相关的知识可参考`MSDN`或者`System Internals 7th part1` security chapter。

不过该方法还是有明显的不足，比如会调用显眼的VirtualAllocEx、WriteProcessMemory、VirtualProtectEx和CreateRemoteThread，通常的EDR都能检测出可能的恶意行为。

> 该方法的详细细节可参考这篇[文章](https://blog.f-secure.com/hiding-malicious-code-with-module-stomping/)。

## Process Hollowing

该方法也比较经典，并被广泛使用，其基本流程如下：

```cpp
CreateProcess(“svchost.exe” , …, CREATE_SUSPENDED, …);
NtUnmapViewOfSection(…) and VirtualAllocEx(…);
For each section:
	WriteProcessMemory(..., EVIL_EXE, …);
Relocate Image*;
Set base address in PEB*;
SetThreadContext(…);
ResumeThread(…);
```

该方法和`Module Stomping`很像，都是替换掉了一个模块，不过有以下三个不同：

- `Process Hollowing`替换的模块是目标EXE程序
- 该方法使用NtUnmapViewOfSection将EXE程序解除映射
- 用ResumeThread来启动恶意程序的入口点

> 该方法的详细实现可参考[这个](https://www.ired.team/offensive-security/code-injection-process-injection/process-hollowing-and-pe-image-relocations#allocating-memory-in-destination-image)。

## Process Doppelganging

接下来描述的几个进程注入方法使用了不同的注入思路，它们之间只有细微的差别，最后会总结它们的异同点。

该方法是2017年在黑客大会介绍的，演讲者首先说明了Process Hollowing涉及的敏感操作和一些不足：

- Unmap目标进程的EXE模块（非常可疑），现代的安全检查一般都有Unmap检查。

- 如果不Unmap，而是直接覆写程序，那么覆写地址的页属性就不是共享的，也很可疑。

  > 页属性共享涉及到操作系统的共享内存机制，这里简单描述一下：
  >
  > 为了节省内存，当一个模块加载进内存时，比如ntdll.dll，操作系统会看该模块是否已被其他进程加载过了（即已经在物理内存中了），如果在，那么操作系统只需要简单地将该物理区域映射到需要加载模块的进程中。因此，这些模块对应的内存是共享的，这些模块内存对应的进程pte(page table entry)会指向一个叫prototypePTE的结构，该结构会指向这些共享的物理内存。
  >
  > 不过，如果我们向模块，比如ntdll.dll，的数据段写入数据，那么这时操作系统就会对ntdll.dll的数据段分配一段物理内存，然后当前进程对应数据段的pte就不会再指向prototypePTE，而是指向操作系统分配的物理内存。
  >
  > 关于内存共享机制的详细描述，读者看参考Windows Internals 7th，第五章的Page fault handling部分。

- 直接覆写程序不够好，那就Unmap后再Remap：

  - 如果remap时的类型不是IMAGE，通过检查节的类型可判定是否可疑

  - 如果remap时的类型是IMAGE，这时可疑的点就不多了。不过因为`Process Hollowing`用SetThreadContext修改了初始线程的执行入口点（ETHREAD.Win32StartAddress），那么我们可以检测其执行入口点是否是ETHREAD.Win32StartAddress。如果不是，那值得怀疑，并且我们可以检测其执行入口点对应的文件名，这样可进一步判定这段内存是否是可疑payload。

    >  检测文件名可通过该字段查看：VAD(ETHREAD.Win32StartAddress).Subsection.ControlArea.FilePointer。

  另外，如果要使用Remap，那就需要一个section，打开section需要一个文件句柄，也就是说Remap需要一个落地的文件，因此采取`process hollowing`时，攻击者很少会使用Remap的方式。

综上所述，Process Hollowing已经不是那么好了，那还有什么其他更隐蔽的方法吗？

于是演讲者介绍了Process Doppelganging，该方法由`CreateFileTransacted`API开始。由于其内容较多，且不易描述，读者可查看这个[PPT](https://www.blackhat.com/docs/eu-17/materials/eu-17-Liberman-Lost-In-Transaction-Process-Doppelganging.pdf)和这个[源码](https://github.com/3gstudent/Inject-dll-by-Process-Doppelganging)和这篇[文章](https://hshrzd.wordpress.com/2017/12/18/process-doppelganging-a-new-way-to-impersonate-a-process/)，这些资料讲得非常详细。

这里归纳了简要的流程：

- 创建一个transaction（事务）

- 打开原程序句柄（通过CreateFileTransacted）

- 向原程序句柄写入恶意代码，根据此时的文件内容，创建一个section

- rollback（回滚）之前的写操作

  > 虽然回滚了文件的内容，但已生成的section映射的内容是修改后的，即内容是payload，解释可参考`Process Herpaderping`小节。

- 通过刚刚创建的section，创建进程（通过NtCreateProcessEx）

- 准备参数到目标进程（跨进程）

- 创建初始线程(NtCreateThreadEx)，之后唤醒线程（NtResumeThread）

以上流程可抽象如下：

```cpp
transact -> write -> map -> rollback -> execute
```

该方法的新颖点在于通过Windows提供的`事务`API，将恶意代码写入打开的文件，并创建一个section，用其创建进程，之后回滚写入操作。这样可以隐藏执行的恶意代码，虽然你查看该进程时（比如procExp），其显示的是原程序的信息，但其真正执行的代码是恶意代码。同时，它比Process Hollowing更隐蔽，因为它不用Unmap，也不需要Remap，它就像正常启动一个进程一样。

最近，我编译了这份代码，发现win10、win8.1和win7都失败了，说明windows已经patch了该方法，以下是win10和win8.1测试的结果：

- 如果覆盖用的是非PE文件，NtCreateSection返回错误，提示无效的PE。

- 如果覆盖用的是PE文件，创建进程成功，不过我们在procExp中看到的是名叫`System Idle Process`，观察该进程信息，其提示“请求的操作是在不再活动的事务的上下文中进行的”。

![image-20220216102919516](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/process_injection/image-20220216102919516.png)

虽然该方法已经失效了，不过它的思路很好。之后介绍的`Process Herpaderping`借鉴了该方法，且目前也是有效的。

> 可能我实践时，代码的参数没设置好，所以没有复现demo里的结果。从现在的恶意攻击看，基于`Process Doppelganging`的攻击很少，不知道是不是因为被patch了。不管怎么说，该方法是一个很好的起点。
>
> 关于实例demo展示，读者可参考[这个](https://www.youtube.com/watch?v=T9pWqYGHqLM&t=27s)。
>
> 关于该方法的描述详情，读者可参考这篇[文章](https://hshrzd.wordpress.com/2017/12/18/process-doppelganging-a-new-way-to-impersonate-a-process/)。

## Transacted Hollowing

该方法借鉴了`Process Doppelganging`的`事务`特性和`Process Hollowing`启动进程的便捷性。通过`事务`特性，可以更好的隐藏恶意代码；通过便捷性，可以免去`Process Doppelganging`创建进程、准备进程参数的复杂过程。

该方法的大致流程是：

- 采用`Process Doppelganging`的前半段，transact -> write -> map -> rollback
- Remap恶意代码的section到目标进程
- 采用`process hollowing`的技巧，通过SetThreadContext和ResumeThread的执行恶意代码

在`Process Doppelganging`小节，我们讲到process hollowing如果要Remap，需要有一个落地的文件。通过事务的回滚，可以免去这个落地的文件。因此，我们可以把`Transacted Hollowing`当做是增强版的`process hollowing`。

> - 关于该方法的代码，可参考这个[仓库](https://github.com/hasherezade/transacted_hollowing)。
>
> - 关于该方法的描述细节，可参考这篇[文章](https://blog.malwarebytes.com/threat-analysis/2018/08/process-doppelganging-meets-process-hollowing_osiris/)。

## Process Ghosting

讲该方法之前，我们先说一下背景知识。

> 在windows操作系统里，如果我们映射了可执行程序，那么可执行程序就不应该被修改，如果尝试修改，则返回错误。但这也是一个限制，即只针对映射过的可执行程序不能被修改，也就是说我们可以打开一个文件、对其设置删除标志、写payload到文件，之后映射文件，最后删除这个文件。
>
> > 注：如果我们以GENERIC_READ和GENERIC_WRITE打开文件，那么映射可执行程序之后，我们还是可以修改文件，这在`Process Herpaderping`将会体现。

该方法与`Process Doppelganging`相似，它们的目的都是做的比`process hollowing`更隐蔽，该方法与

`Process Doppelganging`从实现上几乎一样，唯一的区别就是处理不落地文件的方式：

- `Process Doppelganging`：通过`事务`API打开文件，修改文件（写入payload），创建section，再回滚修改的内容。

- `Process Ghosting`：打开文件，设置删除标志，修改文件（写入payload），创建section，删除文件。这样进程运行时，反病毒软件打不开文件，因此无法做检测。

  > 调用GetProcessImageFileName会返回空字符串。

> - 代码可参考这个[仓库](https://github.com/hasherezade/process_ghosting)。
>
> - 关于该方法的描述细节，可参考这篇[文章](https://www.elastic.co/blog/process-ghosting-a-new-executable-image-tampering-attack)。

## Ghostly Hollowing

了解完`Process Ghosting`，我们来看`Ghostly Hollowing`。与`Transacted Hollowing`类似，该方法也是为了免去创建进程和准备进程参数的复杂过程。于是可以得到以下结论：

![image-20220219142624707](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/process_injection/image-20220219142624707.png)

> - 关于该方法的实现，可参考这个[仓库](https://github.com/hasherezade/transacted_hollowing)。
>

## Process Herpaderping

这是本文描述的最后一个方法，因此我们先来一个方法小总结：

| Type                                   | Technique                                                 |
| -------------------------------------- | --------------------------------------------------------- |
| Hollowing(including `Module Stomping`) | `map or VirtualAlloc -> SetThreadContext -> ResumeThread` |
| Doppelganging                          | `transact -> write -> map -> rollback -> execute`         |
| Herpaderping                           | `write -> map -> modify -> execute -> close`              |
| Ghosting                               | `setDeleteFlag -> map -> delete -> execute`               |
| Transacted Hollowing                   | `transact -> write -> map -> rollback` + Hollowing        |
| Ghostly Hollowing                      | `setDeleteFlag -> map -> delete` + Hollowing              |

该方法的原理、实现都和`Ghosting`、`Doppelganging`类似，读者可以把`Ghosting`和`Herpaderping`都理解为`Doppelganging`的变体。`Ghosting`是删除文件，`Doppelganging`是替换文件的内容（不替换文件），`Herpaderping`是替换文件和文件内容，其结果是反病毒软件检测执行的进程时，其打开的程序文件内容是我们设定的（比如lsass.exe，包括文件签名）。

`Herpaderping`的流程如下：

- 打开一个可读可写的文件
- 向文件写入payload（calc.exe），创建section
- 创建进程A（和Doppelganging一样，使用NtCreateProcessEx）
- 向同一个文件写入伪装的程序，比如lsass.exe
- 关闭并保存文件为output.exe（文件保存至磁盘，磁盘的内容是lsass.exe）
- 准备进程参数，创建线程（这时payload开始执行）

一个有趣的现象是如果我们不关闭执行payload（计算器）的进程A，那么双击output.exe时会启动另一个进程B，弹出另一个计算器。其原因是进程A有一个section，这个section指向的文件路径是output.exe，当我们启动进程B时，操作系统发现路径一样，于是使用了进程A的section对应的SectionObjectPointer，以此实现文件的共享，也就是使用已经映射到内存的output.exe来启动另一个计算器。但如果我们打开output.exe文件，会发现内容又是lsass.exe的。因为文件映射到内存包括data和image类别，而读文件是data类，所以data类对应的内存和image类对应的内存是分开的，也就是说操作系统的内存有两份output.exe文件的数据。下面贴一张关于进程A的section对应的SectionObject示意图。

![image-20220219143458739](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/process_injection/image-20220219143458739.png)

**这里我们通过windbg讲述刚刚的解释**。首先拿到herpaderping的[demo源码](https://github.com/jxy-s/herpaderping)，用visual studio编译完成后，我们启动一个windbg，启动命令如下：

```bash
"C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\windbg.exe" ProcessHerpaderping.exe "E:\my_knowledge\Reverse\Tools\CFF_Explorer\CFF Explorer.exe" E:\tmp\cpp_test_ano.exe
```

其中CFF Explorer.exe是要执行的payload（实际利用场景下，一般没有这样的落地文件，payload是恶意进程解密的出来的），cpp_test_ano.exe是一个合法的可读可写文件。

启动命令后，我们在herpaderp.cpp的142行下断点：

```cpp
wil::unique_handle sectionHandle;
auto status = NtCreateSection(&sectionHandle,
                              SECTION_ALL_ACCESS,
                              nullptr,
                              nullptr,
                              PAGE_READONLY,
                              SEC_IMAGE,
                              targetHandle.get());

//windbg命令如下：
    bp `ProcessHerpaderping!herpaderp.cpp:142`
```

142行是创建section，类型是SEC_IMAGE。在创建section之前，我们观察一下目标文件（targetHadnle）的句柄：

![image-20220219123625433](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/process_injection/image-20220219123625433.png)

打开管理员权限的windbg，启动本地内核调试，查看这个句柄，如下：

```cpp
lkd> !process 0 1 ProcessHerpaderping.exe
PROCESS ffffac0f0ede7080
...
lkd> .process /p ffffac0f0ede7080
Implicit process is now ffffac0f`0ede7080
lkd> !handle ac
...
00ac: Object: ffffac0f2281a300  GrantedAccess: 0012019f (Protected) (Audit) Entry: ffff818476fff2b0
Object: ffffac0f2281a300  Type: (ffffac0efc2d4d20) File
    ObjectHeader: ffffac0f2281a2d0 (new version)
        HandleCount: 1  PointerCount: 32655
        Directory Object: 00000000  Name: \tmp\cpp_test_ano.exe {HarddiskVolume2}
lkd> dt nt!_FILE_OBJECT ffffac0f2281a300
...
   +0x028 SectionObjectPointer : 0xffffac0f`066a6358 _SECTION_OBJECT_POINTERS
...
lkd> dx -id 0,0,ffffac0f0ede7080 -r1 ((ntkrnlmp!_SECTION_OBJECT_POINTERS *)0xffffac0f066a6358)
((ntkrnlmp!_SECTION_OBJECT_POINTERS *)0xffffac0f066a6358)                 : 0xffffac0f066a6358 [Type: _SECTION_OBJECT_POINTERS *]
    [+0x000] DataSectionObject : 0xffffac0f0727b1d0 [Type: void *]
    [+0x008] SharedCacheMap   : 0xffffac0f07911dc0 [Type: void *]
    [+0x010] ImageSectionObject : 0x0 [Type: void *]
```

因为我们打开并写了目标文件，所以SectionObjectPointer的DataSectionObject不为空，即文件内容映射到了内存。

我们单步步过142行，再观察一下SectionObjectPointer：

```cpp
lkd> dx -id 0,0,ffffac0f0ede7080 -r1 ((ntkrnlmp!_SECTION_OBJECT_POINTERS *)0xffffac0f066a6358)
((ntkrnlmp!_SECTION_OBJECT_POINTERS *)0xffffac0f066a6358)                 : 0xffffac0f066a6358 [Type: _SECTION_OBJECT_POINTERS *]
    [+0x000] DataSectionObject : 0xffffac0f0727b1d0 [Type: void *]
    [+0x008] SharedCacheMap   : 0xffffac0f07911dc0 [Type: void *]
    [+0x010] ImageSectionObject : 0xffffac0f0ebd3720 [Type: void *]

```

现在目标文件以Image（可执行程序）这一类别加载进了内存，因此内存中现在有两份目标文件，一份是data类的，一份是image类的。注意这两类现在对应的内容是一样的，之后`ProcessHerpaderping`会向目标文件再写入数据，即修改data类所在的内存，然后关闭目标文件的句柄。此时image类和data类的内容就不同了，但在windows的设计里这是不应该出现的，详情可参考下面推荐的书。

执行`ProcessHerpaderping`的剩下部分，它会等待创建的cpp_test_ano.exe进程退出（实际执行的是CFF Explorer.exe）。这时，如果我们用二进制编辑器打开cpp_test_ano.exe，会发现全是明文数据，不是可执行代码：

![image-20220219133338725](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/process_injection/image-20220219133338725.png)

如果我们双击cpp_test_ano.exe，会发现又弹出了一个CFF Explorer.exe进程，这时观察我们刚刚创建的进程：

```cpp
lkd> !process 0 1 cpp_test_ano.exe
PROCESS ffffac0f2b92f080
...
PROCESS ffffac0f1ccb6080(第二个是刚刚创建的进程)
...
lkd> dt nt!_EPROCESS sectionobject imagefilepointer ffffac0f1ccb6080
   +0x3c0 SectionObject    : 0xffff8184`7b06ecf0 Void
   +0x448 ImageFilePointer : 0xffffac0f`159a2180 _FILE_OBJECT
lkd> dx -id 0,0,ffffac0f0ede7080 -r1 ((ntkrnlmp!_FILE_OBJECT *)0xffffac0f159a2180)
((ntkrnlmp!_FILE_OBJECT *)0xffffac0f159a2180)                 : 0xffffac0f159a2180 [Type: _FILE_OBJECT *]
    [+0x028] SectionObjectPointer : 0xffffac0f066a6358 [Type: _SECTION_OBJECT_POINTERS *]
lkd> dx -r1 ((ntkrnlmp!_SECTION_OBJECT_POINTERS *)0xffffac0f066a6358)
((ntkrnlmp!_SECTION_OBJECT_POINTERS *)0xffffac0f066a6358)                 : 0xffffac0f066a6358 [Type: _SECTION_OBJECT_POINTERS *]
    [+0x000] DataSectionObject : 0xffffac0f0727b1d0 [Type: void *]
    [+0x008] SharedCacheMap   : 0x0 [Type: void *]
    [+0x010] ImageSectionObject : 0xffffac0f0ebd3720 [Type: void *]
```

刚创建的进程对应的ImageSectionObject和之前在`ProcessHerpaderping`进程看到的结果一样，代表刚创建的进程和`ProcessHerpaderping`启动的cpp_test_ano.exe进程共享了image类对应的内存，共享了对应的CFF Explorer程序代码。

> 关于上面的解读，这涉及到windows操作系统对section的管理，比如文件的映射细节和文件的缓存管理，有兴趣的读者可以参考 `Windows Internals 7th part1` 第五章内存管理的section小节和`Windows Internals 7th part2`第十一章缓存管理器部分。

> - 该方法的源码可参考这个[仓库](https://github.com/jxy-s/herpaderping)。
> - 该方法的作者用windbg进一步分析了共享的更多细节，可参考这个[文档](https://github.com/jxy-s/herpaderping/blob/main/res/DivingDeeper.md)。

## Conclusion

虽然进程注入在不断更新，不过安全厂商也在与时俱进，目前很多安全厂商都有这些方法的监控了（比如上面提到的分析文章，大部分是安全厂商写的）。从`Process Doppelganging`开始，我们能看到新的方法都是源于操作系统的不足，并慢慢衍生，可能以后的进程注入会越来越底层，越来越复杂。

本文涉及的细节很多，不能面面俱到，推荐读者看本文各个小节的推荐文章，最后再来看本文，相信读者会有更多的收获。

