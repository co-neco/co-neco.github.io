---
title: 浅谈VMP、SafeEngine、Themida反虚拟机
categories:
  - Technology
  - Reverse
date: 2021-08-01 18:07:31
tags:
---

这里浅谈一下VMP、Safengine和Themida的反虚拟机的分析过程，关于反调试下面会说下值得注意的地方。

VMP的反调试请参考https://bbs.pediy.com/thread-226455.htm，Safengine和Themida的反调试与VMP差不多。

分析的VMP版本为3.0.9，Themida版本为2.4.6.30，Safengine不知道是什么版本了，程序是 32bit 。

> 关于64bit程序，反调试和反虚拟机都更简单。其中反调试只包含IsDebuggerPresent、NtGlobalFlag、CheckRemoteDebuggerPresent。不过需注意的是程序在OEP后，IsDebuggerPresent之前保存NtGlobalFlag标志，在IsDebuggerPresent之后同时检测BeingDebugged和NtGlobalFlag标志，最后调用CheckRemoteDebuggerPresent。反虚拟机则只有注册表检测，没有in指令检测，因此只需修改注册表，就可在虚拟机运行。

### 反调试

#### VMP反调试

  VMP的某些版本有tls保护，该tls用于检测调试器，具体方法不明。目前排除了tls对软件断点、硬件断点、SEH、NtGlobalFlag、BeingDebugged、Heap结构的ForceFlags和Flags检测，包括堆中的调试记号（0xbababa,badf00d等）。虽然不明检测方法，但要过掉还是挺简单的，直接跳过该tls。跳过的步骤是用调试器启动程序，在加载ntdll后，把TLS的DataDirectory清零，让系统读不到tls callback，当走到OEP时，再还原。当然，如果程序没有文件完整性检测，可以直接修改文件中TLS的DataDirectory项。

### 反虚拟机

#### VMP反虚拟机

  从结果来说，VMP反虚拟机只使用了一个方法，特殊指令，该特殊指令是cpuid。检测原理是赋eax为1，执行cpuid后，如果ecx的31st位为0，表示真机，否则为虚拟机。

  从分析过程来说，主要分为3步。 一是分析虚拟机框架，二是逐步接近特殊指令，三是定位特殊指令，如下图：

![img](clip_image001.png)

- 虚拟机框架：

  根据初步VMP的分析，该VMP无dispatcher，全程是用push edi，ret来调整执行流程，其中的edi由mov …,dword ptr [esi]转换而来。VMP的单元步骤为一对，如下：

``` c
...
lea esi, [esi-4]
mov eax, dword ptr [esi]
decode eax
add edi, eax
jmp edi      //跳转到handler
...
dec esi
movzx eax, byte ptr [esi]
handler      //具体执行内容
...
```

其中值得注意的是字节码的表示，esi和edx轮换表示字节码的当前获取地址，这些地址是一段一段的，且可以重复利用，如下图：

![img](clip_image004.png)

- 逐步接近特殊指令：

  找到存放字节码段首地址的栈地址。因为字节码段是乱序且繁多的，手动跟踪非常缓慢。之后注意到在ebp的一个相对偏移处存有esi或edx的字节码段首地址，且ebp相对一段时间是固定不变的，因此可在这个相对偏移下写断点。果然，这个断点被触发了一千多次，由于堆栈的成长，ebp会超过VMP自己的虚拟栈，因此需要调整ebp，这时存放字节码段首地址的相对偏移会稍有变化，因此需要重复几次找这个“相对偏移”的步骤。最后越来越接近特殊指令。

  > 注：这部分本应更具体一点的，无奈是以前的文章，大家将就看一下吧，感觉下大概。

- 定位特殊指令：

  通过程序检测到虚拟机的附近代码寻找特殊指令。虽然第二步的结果很接近特殊指令了，但在VMP中，这个距离还是非常长的，因此需要另找方法。具体方法是定位程序检测到虚拟机的错误点，然后一步一步逼近，最后用x32dbg的trace功能扫描代码，找到特殊指令。其中，定位错误点根据“Sorry, this application cannot run under a Virtual Machine.”提示语句寻找，因为这段文字被存在栈中的一个固定位置，所以只需在此处下断点就能判断何时触发的错误点，然后向上回溯，最终找到特殊指令。

- 快速定位：

  以上是定位的过程，这里提供一个快速的定位方法。由于程序对VM化的代码不会再做加密，因此可以在vm段直接内存搜索，找到cpuid，注意VMP一般会用一次或两次该指令来检测。

- 过掉cpuid：

  一般执行cpuid时，ecx的31st位为0，所以cpuid直接用两个nop替换即可。

#### Safengine反虚拟机

使用in指令和RegQueryValueExA检查SystemManufacturer(在注册表里)，in指令的原理请参考https://bbs.pediy.com/thread-225735.htm。这里说下如何定位in指令和过掉。

in指令在真机中会产生0xC0000096异常，而在虚拟机中不会产生异常。因此定位in指令需要在真机的调试器中运行，但前提是你要知道它反虚拟机使用的是in指令，这个就需要各种尝试了（因为safengine首先是反调试，然后再是反虚拟机，所以分析反调试时很轻松就能发现in指令）。

定位到后，就是过掉了。为了说明过掉方法的原理，这里需要再讲下in指令。in在真机中产生异常，执行程序的SEH，在SEH中会将eip重新赋值。该过程就像一个跳转，在in指令的地址处有一条jmp指令的感觉。而在虚拟机中，不会产生异常，那么就会进入检测到虚拟机的分支。

稍微了解了in指令后，现在说明两个过掉方法。一是换成int3，二是重设eip。关于一，in和int3指令只占用一个字节，且int3也可产生异常，因此非常合适。但不排除程序的SEH会检测该异常的ExceptionCode，如果是这样，那就用第二种方法。关于二，调试程序，走到in指令后（下硬件断点），手动给eip赋值，该值是SEH里指定的值。

#### Themida反虚拟机

##### 检测方法

-  注册表检测

   两次使用in指令和RegQueryValueExA检查注册表内容。其中注册表内容包括以下三点：
   
   - HKEY_LOCAL_MACHINE\HARDWARE\DESCRIPTION\System\VideoBiosVersion(一般虚拟机中没有,不过没有该项也不会导致虚拟机被检测到)
   
   - HKEY_LOCAL_MACHINE\HARDWARE\DESCRIPTION\System\ SystemBiosVersion
   - HKEY_LOCAL_MACHINE\SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0000\DriverDesc

- in指令检测

  两次in指令的使用中ecx分别为0x14和0xA，0x14是检查返回的eax，0xA是检查返回的ebx。其中：
  
  - ecx为0x14时，VMware® Workstation 14 Pro返回的eax为0x800，在真机中会跳到SEH，将eax赋值为0
  - ecx为0xA时，虚拟机中的ebx为 'VMXh'，在真机中进入SEH，并在SEH中直接修改eip跳转

##### in指令定位过程

- 检测相关函数

  因为Themida没有用PSAPI.dll、IPHLPAPI.dll、shlwapi.dll，所以能用来反虚拟机的函数比较有限，除了与注册表相关的函数，剩下的是检查固件信息的函数，不过设断点后都没有触发，断点如下：

  ```c
  ba e1 KERNELBASE!GetSystemFirmwareTable
  ba e1 KERNELBASE!EnumSystemFirmwareTables
  ```

  之后我用APIMonitor监控Themida对API的调用，除了注册表相关函数，确实没有其他用于检测虚拟机的函数了。因此我猜测剩下的虚拟机检测方法不是用的函数，而是特殊指令。

- 搜索cpuid指令

  让程序运行，在Themida的可执行段搜索cpuid指令，在可能的指令处下硬件断点，结果没有命中。因为Themida有SMC，所以在代码解密之后搜索cpuid，尝试下断点，但仍然没有命中。 

- 跟踪错误提示字符串并尝试分析多线程

  跟踪MessageBoxExA引用的提示字符串时，发现多线程SMC。之后分析多线程时，无法掌控主线程的执行进度。Themida在检测到虚拟机后，会用MessageBoxExA弹框，于是我开始跟踪“Sorry, this application cannot run under a Virtual Machine”字符串，发现该字符串是多次解密后产生的结果。之后我回溯该字符串的解密过程，但由于多线程之间频繁的相互切换，我无法持续单步跟踪主线程，导致当线程切换后，主线程已经执行到不可预估的地方了。
  
  > 关于跟踪主线程，还有两点需要解释：
  >
  > - 第一是无法保持一直跟踪主线程，因为主线程执行到不同代码片段时会进入死循环，等待其他的某个线程修改对应的死循环代码，因此仅仅是挂起除主线程的所有进程是无法继续分析的，必须在某一点唤醒其他解密线程。
  >
  > - 第二是线程切换时不能预估主线程的执行进度。当主线程需要执行待解密的代码时，会首先标记一个事件句柄（即告诉其他线程，你们可以执行了），然后调用Sleep(0)，释放掉当前分配给自己的执行时间，以让其他线程被调度。而其他线程有部分是调用Sleep，正准备被唤醒，有部分是用WaitForSingleObject等待某事件句柄，该事件句柄正是主线程标记的事件句柄。
  >
  >   在这个过程中，如果对主线程Sleep(0)的下一条汇编指令下断点，结果就是断点会被命中，但往往被命中的线程不是主线程，而是同样调用Sleep、等待被唤醒的其他线程。因此，这里不应该在主线程将被唤醒的汇编代码处下断点，即使断点被命中，也很可能是其他线程被命中。因为除主线程，还有大概25个线程等待被唤醒，其中调用Sleep等待被唤醒的数量可能有7、8个。

- 尝试分析虚拟机框架

  分析虚拟机框架，尝试定位提示字符串产生的过程，找到反虚拟机的特殊指令。因为无法精确跟踪主线程，所以我想分析Themida的虚拟机框架，进一步分析细节，找到提示字符串的解密以及产生过程。在看雪搜索相关帖子后，发现分析成本很大，无法快速达到定位特殊指令的目的，因此需要另找思路。

- 尝试根据虚拟机配置来定位特殊指令

  Themida的虚拟机检测可以通过设置VMware选项过掉(不过我尝试没成功)，比如：
  
  ```c
  disable_acceleration = "TRUE"
  monitor_control.restrict_backdoor = "TRUE"
  ```
  
  于是我想弄懂这两句的原理，以此定位特殊指令。通过一段时间的搜索，发现这些语句可能与虚拟机解释执行指令有关，不会与某条特定的汇编指令产生关联（因为找不到官方文档的说明，无法确定该猜想）。因此通过虚拟机配置寻找特殊指令大概是不可行的。

- 与真机对比并锁定关键条件跳转

  对比真机和虚拟机的执行情况，找到关键代码段；对比这两份代码段，发现判断虚拟机的标志。

  单独分析虚拟机的情况无法找到特殊指令，那在真机中执行相同步骤，以此来寻找异同点，以下为两个关键点：

  - 在真机和虚拟机中，“Sorry, this application cannot run under a Virtual Machine”字符串都会被解密。在虚拟机的分析中，我设定了一个前提，即解密该字符串意味着Themida发现了虚拟机。

    但真机的这一现象，瞬间颠覆了我的想法，看来准备工作没做充分。我开始在虚拟机和真机中交替分析程序，找到了两种环境下程序的分叉点，从该分叉点继续执行大概23000条汇编指令，虚拟机会执行到MessageBoxExA并报告发现虚拟机，而真机则不会报告。

  - 对比代码段，发现关键条件跳转。使用x32dbg的trace功能，把两种环境下从分叉点执行的23000行代码dump下来，然后用BCompare进行文本比较，发现大概在1500行后，程序判断eflag的ZF标志，ZF为1对应真机，ZF为0对应虚拟机。从eflag的比较处开始回溯，发现一句关键的代码

    ```c
    cmp [addr], 0
    ```
  
  addr指向的地址处保存了一个标志，该标志是用来存储某个结果的。如果是虚拟机，该标志为1，如果是真机，则为0。
  
  之后继续回溯，找到了该标志是在哪片代码被设置的。这片代码只是在设置标志，无法得知为何会设置该标志。
  
  由于Themida的跳转很多，不清楚程序是从哪跳转到这片代码的，于是再使用x32dbg的trace功能，发现在程序调用GetNativeSystemInfo和GetVersion后不久（大概200，300行），就跳到了这片代码，这时已经看到了in指令，即成功定位到in指令。

- 两次in指令检测
  - 第一次检测

    ``` c
    in eax,dx  //ecx为0x14，用于获取VMware中VX端口的memory size
    pop dword ptr fs:[0]  //两种环境下都会达到该指令
    push 3D193AC9
    mov dword ptr ss:[esp],eax  //将结果赋到栈中,在真机中会进入SEH，把eax设为0，在虚拟机中返回的eax为0x800。
    xor eax,dword ptr ss:[esp]
    xor dword ptr ss:[esp],eax
    xor eax,dword ptr ss:[esp]
    pop esp
    cmp eax,0  //若为真机，eax为0，若为虚拟机，eax大于0
    jbe 5B775D
    cmp dword ptr ss:[ebp+17BA1689],1  //[ebp+17BA1689]的值在两种环境下均为1
    jne 5B775D
    mov dword ptr ss:[ebp+17BA2DBA],1  //只有虚拟机会到达此处，设置标志位
    ...
    5B775D xxxx
    ```

  - 第二次检测:

    ``` c
    in eax,dx  //ecx为0xA，用于获取VMware版本
    cmp ebx,564D5868  //虚拟机会执行到此处，返回的ebx为0x564D5868
    jne 5B4BE2    
    mov dword ptr ss:[ebp+17BA2DBA],1  //只有虚拟机会到达此处，设置标志位
    (5B4BE2) pop dword ptr fs:[0]  //真机会从in指令转到SEH，最后修改eip跳到这里
    add esp,4
    cmp dword ptr ss:[ebp+17BA2DBA],0
    jne 5B3EA2  //虚拟机中，跳转到5B3EA2，执行虚拟机的分支，否则继续执行 
    ```

  最后，in指令的快速定位和Safengine一样，在真机中跟踪异常，直到发现in eax, dx产生的异常。之前我在真机中没有定位到in指令的原因是0xC0000096的异常太多了，大多数是由Themida的sti指令产生的，于是当时我就偷懒没有挨个查看产生异常的指令。

 

##### Themida反虚拟机需注意的点

- 真机和虚拟机中都会解密“Sorry, this application cannot run under a Virtual Machine”这段文字，所以不能跟踪这段文字来找到in特殊指令。另外Themida使用MessageBoxExA(不管程序是否使用Unicode)输出错误信息。

- Themida使用多线程SMC，使得主线程边运行边执行被解密的代码，多线程之间通过事件对象同步。（解密代码一般由其他线程完成，不过主线程也会解密一部分代码）。从结果来说，in指令是解密代码后才出现的，虽然程序运行后会解密出来，但因为 in eax，dx 只需一个字节，所以即使解密代码后，搜索时结果也会有很多无关信息，直接导致无法判定。

- Themida会使用很多sti指令，该指令会触发异常，且ExceptionCode和in指令的ExceptionCode是一样的(因为sti指令较多，最初在真机中没有枚举所有的异常，所以没发现in指令。当最后发现是in指令时，才在真机中证实了in指令的使用)。因为SEH的不同，sti的作用可能不一样，不过大多数都是将eip加1。另外，要从sti跟踪到SEH，比如断到ntdll!KiUserExceptionDispatcher，需要下软件断点，不能下硬件断点。在刚进入 ntdll!KiUserExceptionDispatcher时，调试寄存器的值为0，等执行到程序的SEH时，调试寄存器的值才会恢复原来的值。

- 分析主线程时，由于多线程之间会经常跳转，因此当跟踪主线程的关键代码时，要将除主线程的所有线程挂起。