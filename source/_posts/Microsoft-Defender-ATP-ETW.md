---
title: "[翻译] Microsoft Defender ATP ETW"
categories:
  - Technology
  - Reverse
date: 2021-11-09 12:56:25
tags:
  - Translation
  - Microsoft Defender
  - ETW
  - Privilege Escalation
---

# [翻译]从接到告警到发现驱动漏洞：Microsoft Defender ATP 检测出提权漏洞

> -> [原文链接](https://www.microsoft.com/security/blog/2019/03/25/from-alert-to-driver-vulnerability-microsoft-defender-atp-investigation-unearths-privilege-escalation-flaw/)

随着Microsoft团队不断增强内核层的安全性、以及提升内核组件被利用的门槛，第三方开发的驱动渐渐成为了攻击者青睐的目标，同时第三方驱动也成为了漏洞分析的一个重要试验地。

一个签名的第三方驱动如果有一个漏洞，那么它可能会带来严重的影响：这个漏洞可能被攻击者利用，用来权限提升，或者用来过掉驱动签名验证。相对于用一个操作系统自身的0day漏洞来进行攻击，签名的第三方驱动的漏洞更容易被利用。

计算机厂商通常会为设备配备一些软件和工具，用来辅助设备的管理。这些软件和工具（包括驱动）通常都包含一些模块，这些模块工作在R0层。这些每一个默认被安装的组件都应该和内核组件一样安全，即使一个存在风险的组件都可能让整个内核安全设计崩坍。

在调查[Microsoft Defender Advanced Threat Protection](https://www.microsoft.com/en-us/windowsforbusiness/windows-atp?ocid=cx-blog-mmpc)内核探测器发现的告警时，我们就发现了这样一个有风险的驱动。我们分析了一个华为开发的设备管理驱动，这个驱动存在一些异常行为。更进一步分析之后，我们发现了一个设计缺陷，这个缺陷可以引发本地提权。

我们把这个漏洞（CVE-2019-5241）报告给华为之后，华为立刻回复我们，并积极与我们确认了漏洞信息。2019年1月9日，华为修复了这个漏洞：https://www.huawei.com/en/psirt/security-advisories/huawei-sa-20190109-01-pcmanager-en.

在这篇文章里，我们将分享这一过程：从调查Microsoft Defender ATP的告警到发现上述漏洞，再到与驱动开发厂商合作，最后共同保护用户。

## Microsoft Defender ATP监测到内核发起的代码注入

从Windows 10, version 1809开始，内核新添了一些新的监测器（基于事件追踪--ETW），用于追踪从内核发起的UserAPC代码注入。这种方式使得一些内核攻击更容易被监测到。正如我们之前深入分析的[一篇文章](https://cloudblogs.microsoft.com/microsoftsecure/2017/06/30/exploring-the-crypt-analysis-of-the-wannacrypt-ransomware-smb-exploit-propagation/)，WannaCry利用DOUBLEPULSAR这个内核后门，向用户空间注入了代码（payload）。其原理是DOUBLEPULSAR从内核复制了一段代码到lsass.exe的用户空间。随后，DOUBLEPULSAR又向lsass.exe插入了一个UserAPC，去执行这段代码。

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/translation/ATP_ETW/figure-01-WannaCry-user-APC-injection-technique-schematic-diagram-768x384.png)

虽然UserAPC代码注入不是新知识了 (看 [Conficker](https://www.microsoft.com/en-us/wdsi/threats/malware-encyclopedia-description?Name=Win32/Conficker) 或者 [Valerino’s earliest proof-of-concept](https://community.osr.com/discussion/88852))，但检测内核的恶意行为还是很难的。自从PatchGuard引入之后，对NTOSKRNL模块进行挂钩已经不允许了，驱动也因此没有官方方法去获取那些挂钩操作对应的通知了。因此，没有合适的方法，剩下的唯一可持续迭代的策略就是做内存分析，但内存分析很复杂。

最近新加入的一些内核监测器就是为了解决这类内核分析问题。

Microsoft Defender ATP使用这些监测器去监测可疑的内核行为，比如说注入代码到用户空间。通过新监测器发现的一个可疑行为帮我们定位到了一个漏洞，不过这个可疑行为与WannaCry、DOUBLEPULSAR或者其他内核攻击是不一样的。

## 分析由内核模块发起的一个可疑代码注入

当监测与内核攻击相关的告警时，一个告警引起了我们的注意：

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/translation/ATP_ETW/figure-02-2-Microsoft-Defender-ATP-kernel-initiating-code-injection-alert.png)

这个告警处理树展示了在services.exe的进程空间，异常内存的分配和代码执行。当进一步分析之后，我们发现在另一台机器上，几乎是相同的时间，一个相同的告警被触发了。

为了进一步理解这个异常行为，我们观察了内核监测器检测到的原始信号。这次观察中我们发现：

- 一个系统线程调用*nt!NtAllocateVirtualMemory*在*services.exe*进程空间分配了一个页（大小为0x1000），页属性是*PAGE_EXECUTE_READWRITE* 
- 这个系统线程然后调用*nt!KeInsertQueueApc*向*services.exe*插入了一个UserAPC，APC的NormalRoutine指向刚分配的页的起始地址，NormalContext指向该页偏移0x800处。

从内核拷贝的这段代码被分为两个部分：一个shellcode（NormalRoutine）和一个参数块（NormalContext）。分析到这里，上述行为的可疑程度值得我们继续分析下去。我们的目标是探究插入UserAPC的内核代码为何要这么做。

## 追根溯源

在用户层的恶意行为中，通过进程的执行环境，我们可以分析恶意代码的行为和攻击链的其他阶段。但内核的恶意行为就更复杂了。内核本身的设计是异步的，回调函数可能在任何一个进程空间被执行，这使得进程空间信息对于恶意分析没有多大用。

因此，我们尝试去找一些间接证据，关于加载进内核的第三方代码的证据。通过观察计算机的时间线，我们发现几个第三方驱动比平常要提前一点加载。

根据这些驱动的路径，我们发现它们都与华为的PC Manager应用有关，PC Manager是一个用于Huawei MateBook平板的设备管理软件。PC Manager的安装包在华为官网可获取，于是我们下载了PC Manager并开始进一步分析。对于每一个华为驱动，我们用*dumpbin.exe*去观察它导入的函数。

然后我们发现了一个相关函数：

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/translation/ATP_ETW/figure-03-dumpbin-utility-used-to-detect-user-APC-injection-primitives.png)

## *HwOs2Ec10x64.sys*：驱动的反常行为

最后我们追踪到了触发告警的内核代码，以下是分析过程。

一般一个设备管理软件几乎只执行与硬件相关的任务。设备管理软件与配备的驱动合作管理具体的OEM硬件。那么为什么这个驱动会执行反常的行为呢？为了回答这个问题，我们逆向了*HwOs2Ec10x64.sys*驱动。

我们的出发点是实现UserAPC注入的函数。我们发现了这样一条代码流程：

- 在某个进程分配RWX页
- 在目标进程获取CreateProcessW* 和 *CloseHandle*的函数地址
- 从驱动拷贝一段代码和疑似参数的数据块到分配的页中
- 对目标进程执行UserAPC注入

参数块包含获取的函数地址和一个字符串，通过分析，该字符串判定是一个命令行：

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/translation/ATP_ETW/figure-04-User-APC-injection-code.png)

这个APC的NormalRoutine是一段shellcode，其调用*CreateProcessW*，用刚提到的命令行创建了一个进程。这意味着通过APC向*services.exe*实施的代码注入的目的是生成一个子进程。

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/translation/ATP_ETW/figure-05-User-shellcode-performing-process-creation.png)

观察交叉索引，我们发现代码注入是由一个创建进程的通知回调引起的，这个回调的Create参数是FALSE，意味着这个回调指的是某进程的结束。

但这个命令行的具体内容是什么呢？我们附加了一个内核调试器，并在*memcpy_s*下了一个断点，*memcpy_s*用于从内核拷贝参数到用户空间。观察内存，我们发现创建的子进程是华为已安装的服务*MateBookService.exe*，创建子进程时带了*“/startup”*参数。

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/translation/ATP_ETW/figure-06-2-Breakpoint-hit-on-the-call-to-memcpy_s-copying-shellcode-parameters.png)

为什么一个合法的服务要通过这种方式启动呢？观察*MateBookService.exe!main*函数，该函数会检测启动该进程时是否有*“/startup”*参数，如果有，就判断该服务是否被停止了。这意味着有一个看门狗，用于保证PC Manager的主服务正常运行。

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/translation/ATP_ETW/figure-07-MateBookService-exe-startup-code-path.png)

分析到这里，最后需要确定的是退出的进程，同时也是引发代码注入的这个进程是否就是*MateBookService.exe*。

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/translation/ATP_ETW/figure-08-Validating-terminated-process-identity.png)

观察用于决定是否注入代码到*services.exe*的代码片段，该代码片段用了一个全局列表，这个全局列表包含了需要监控的进程名。通过在这个循环里设置一个断点，我们发现这个全局列表只有一个元素，是*MateBookService.exe*。

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/translation/ATP_ETW/figure-09-Breakpoint-hit-during-process-name-comparison-against-global-list.png)

*HwOs2Ec10x64.sys* 驱动也有进程保护，防止自身被恶意攻击。任务终止*MateBookService.exe*进程的行为都会失败，失败原因是*Access Denied*（拒绝访问）。

## 利用*HwOs2Ec10x64.sys*的看门狗机制

接下来我们的分析是确定攻击者是否可以修改这个全局列表。我们发现了一个IOCTL处理函数，这个函数可以向全局列表添加元素。当MateBookService.exe服务启动时，它似乎会通过这个IOCTL来注册自己。这个IOCTL会发向驱动控制设备，这个设备通过它对应的驱动入口函数（*DriverEntry*）创建。

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/translation/ATP_ETW/figure-10-HwOs2Ec10x64.sys-control-device-creation-with-IoCreateDevice.png)

因为设备对象是通过*IoCreateDevice*创建的，所以每个人对这个设备都有读写权限。另外一个重要的发现是这个设备没有禁止同时访问，所以可以同时打开多个这个设备的句柄。

然而，当我们尝试获取*\\.\HwOs2EcX64*的句柄时，我们失败了，错误码是537，代表*“应用程序验证器在当前进程发现一个错误”*。这个驱动拒绝了我们获取设备句柄的请求。我们是如何获取设备句柄的呢？它肯定是通过CreateFile获取的。也就是说，获取句柄必会走到*HwOs2Ec10x64.sys* 的*IRP_MJ_CREATE*分发函数。

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/translation/ATP_ETW/figure-11-IRP_MJ_CREATE-dispatch-routine.png)

这个函数通过进程的路径名来验证当前进程是否在白名单（比如：*C:\Program Files\Huawei\PCManager\MateBookService.exe*）。简单地检测程序的进程名不能保证进程的身份不变。一个被攻击者控制的*MateBookService.exe*进程实例仍然有打开*\\.\HwOs2EcX64*设备的权限，也能够调用对应的一些IRP函数。攻击者可利用这种方式向*\\.\HwOs2EcX64*设备的全局列表注册一个自己设置的元素，也就是一个程序路径。因为一个父进程有子进程的所有权限，即使一个低权限的代码也可以创建被感染的*MateBookService.exe*进程，然后想这个感染的进程注入代码。在我们的POC中，我们使用了进程傀儡技术。

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/translation/ATP_ETW/figure-12-Procmon-utility-results-showing-POC-process-start-exit-IL.png)

因为被“照顾”的进程退出时，它们会被看门狗盲目地重启，所以攻击者控制的程序也会被services.exe重启，这意味着攻击者控制的进程的权限是LocalSystem用户和权限一样，也就是得到了提权。

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/translation/ATP_ETW/figure-13-Procexp-utility-process-tree-view-showing-LPE_POC-running-as-LocalSystem.png)

## 漏洞的及时响应和保护用户

我们有一个能利用的POC，用来将攻击者控制的进程提权之后，我们及时将这个bug通过Microsoft Security Vulnerability Research ([MSVR](https://www.microsoft.com/en-us/msrc/msvr)) 程序通知了华为。这个漏洞被取名CVE-2019-5241。同时，我们通过建立能产生告警的监测机制，保护了我们的用户，避免受到*HwOs2Ec10x64.sys*看门狗漏洞的攻击。

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/translation/ATP_ETW/figure-14-2-Microsoft-Defender-ATP-alerting-on-the-privilege-escalation-POC-code.png)

## 利用另一个IOCTL处理函数

现在，我们可以轻松地从用户空间调用*HwOs2Ec10x64.sys*驱动的IOCTL处理函数了。根据这一点，我们又寻找了是否可以被利用的点，结果是又找到了一个。这个驱动提供了映射任何具有读写属性的物理页到用户空间。通过执行IOCTL的处理函数，我们可以运行一个低权限的进程，去读写其他进程、甚至内核空间的内存，这意味着整个机器的数据都被泄漏了。

我们也和华为解决了第二个漏洞。这个漏洞被取名为CVE-2019-5242。华为在相同的安全警告通知里也公示了这个漏洞：

https://www.huawei.com/en/psirt/security-advisories/huawei-sa-20190109-01-pcmanager-en。

我们在二月的*Blue Hat IL*会议中发表了我们的研究成果，可以从[这里](https://www.youtube.com/watch?v=Ltzye0Cj9G8&feature=youtu.be)获取视频，从[这里](https://msrnd-cdn-stor.azureedge.net/bluehat/bluehatil/2019/assets/doc/Who%20is%20Watching%20the%20Watchdog%20Uncovering%20a%20Privilege%20Escalation%20Vulnerability%20in%20OEM%20Driver.pdf)获取演讲稿。

## 总结

虽然原始的告警看起来不是太有用，因为没有检测到类似DOUBLEPULSAR的内核威胁。但这个告警确实引起了我们的注意，并让我们发现了两个漏洞。我们发现的这两个驱动漏洞证明了我们在设计软件和产品时，应把安全考虑在内。安全的底线是必须坚守的，攻击面应该尽可能的被缩小。在上述的例子里，如果我们足够小心，我们是可以避免这些错误的：

- 被驱动创建的设备对象应该被赋予一个系统读写权限的DACL（因为只有生产厂商的服务才会直接与对应的驱动交互）
- 如果一个服务需要一直保持运行，开发者应该先确认操作系统是否有对应的功能，如果没有，再自己实现对应的机制
- 用户模式不应该执行特权操作，比如写如何物理页。如果确实需要，那也应该在约定好的、与硬件相关的场景下由驱动来完成对应的写操作

微软的 [driver security checklist](https://docs.microsoft.com/en-us/windows-hardware/drivers/driversecurity/driver-security-checklist)（驱动安全检测名单）给驱动开发者提供了一些指南，以减少驱动被恶意利用的风险。

驱动漏洞的发现也说明了 [Microsoft Defender ATP](https://www.microsoft.com/en-us/windowsforbusiness/windows-atp?ocid=cx-blog-mmpc)监测器的强大。这些监测器会通知可疑的行为，并给安全分析团队提供相应的信息，和一些相关的分析工具。

可疑行为一般都表明一些不怀好意的攻击手段。在这个例子中，它们代表了一个可以被利用的错误设计。

而Microsoft Defender ATP提示了这个安全错误，并保护用户免受可能的真实攻击。

***Amit Rapaport\*** *(**[@realAmitRap](https://twitter.com/realAmitRap))*
*Microsoft Defender Research team*