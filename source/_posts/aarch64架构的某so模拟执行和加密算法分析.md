---
title: aarch64架构的某so模拟执行分析
categories:
  - Technology
  - Reverse
date: 2024-07-16 18:50:07
tags:
  - Android
  - qiling
---

## 本文目的

在用Windows平台使用qiling模拟执行框架中遇到了诸多困难，有些问题并没有查询到解决办法，于是记录此篇文章，希望能给到大家一些参考。

以下列举了本文想阐述的内容点：

- aarch64 so基于qiling如何做模拟执行
- Windows上使用qiling的一些问题解决
- 算法中虚拟机的模拟执行

> 本文尽可能从初学者的视角来阐述，初学者可以自行实践。

## 分析目标

最近需要分析一个libxx.so的加密算法，发现是aarch64的so，于是有以下三个思路

- 用IDA静态分析
- 用调试器调试，跟踪算法流程
- 用unidbg、unicorn做模拟执行

## 选择模拟执行的原因

### 静态分析成本过高

用IDA看了一下加密函数，有点像嵌套的控制流平坦化，但实际上是一个虚拟机，这样静态分析的难度就提升了不少。
![alt text](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image.png)

### 用调试器调试

最初的想法是编译一个ARM64的可执行文件，然后加载libxx.so，调用加密函数来调试。通过IDA查看字符串信息，发现是ndk+llvm编译的so，给安卓平台使用的。于是想安装一个ARM64的ubuntu虚拟机来调试，但ubuntu似乎没提供ARM64的客户机，只有服务端版本。可能准备其他发行版本的linux（比如centos）可以调试，但想到模拟执行在trace等功能相较于调试器会更好用点，所以最后选择了用模拟器的方式。

> 现在想来，可能用Android Studio写个app，然后用lldb来调试可能是最稳定的调试方式。大家有什么其他好的意见呢？

### 模拟执行

unidbg基于unicorn，可以模拟执行安卓的so，能很好的满足需求。但从Bet4的[这篇文章](https://bbs.kanxue.com/thread-272605.htm)中，unidbg也存在模拟缺陷，于是我选择了qiling作为模拟执行框架，详细理由可参考上文提及的Bet4的文章。
从官方文档了解qiling的大致使用方法后，发现qiling有自带的qdb调试器，不过不支持多线程，而Bet4开源的udbserver支持多线程，配合pwndbg效果图如下（图来自Bet4的帖子）：
![alt text](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/pwndbg.png)
之后又发现qiling提供了IDA插件，方便直接在IDA中模拟执行so。因为分析算法会经常参考IDA的一些视图，如果用udbserver的话，会在gdb调试器和IDA之间频繁切换，最后我选择使用qiling的IDA插件来“可视化地调试so”。

## ARM64 demo运行

在qiling源码的examples\rootfs\arm64_linux\bin目录下，有很多arm64程序可供模拟执行，lib目录下包含了程序对应的动态链接器，ARM64对应的动态链接器一般是ld-linux-aarch64.so.1。这个动态链接器非常关键，它负责程序依赖的库的加载和程序自身的重定位等功能。

接下来拿bin目录下的arm64_hello举例，演示如何用IDA插件来模拟执行一个aarch64的so，arm64_hello的功能是输出“Hello, World!”字符串，然后退出。官网的完整demo可查看[这个链接](https://docs.qiling.io/en/latest/ida/)。

### 初始化qiling环境

用IDA加载arm64_hello，选择"File->Script file..."加载qiling\extensions\idaplugin\qilingida.py。

> 在我的电脑上软连接无法生效，可能qiling只测试了Linux，所以这里直接用IDA加载脚本的方式来加载qilingida.py。

然后在IDA汇编视图右键->Qiling Emulator->Setup（后续简称`Qiling->`），加载IDA插件，这里使用qiling默认的辅助脚本（custom_script.py）。在IDA中的一些自动化逻辑都可以放到该脚本中，比如添加一些syscall或者针对某地址的hook到该辅助脚本，之后会举例脚本的用法。

![image-20240716201551107](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240716201551107.png)

俗话说万事开头难，运行demo就出现加载失败了，如下：

```
  File "C:\Program Files\Python39\lib\site-packages\qiling\os\linux\linux.py", line 30, in __init__
    super(QlOsLinux, self).__init__(ql)
  File "C:\Program Files\Python39\lib\site-packages\qiling\os\posix\posix.py", line 190, in __init__
    super().__init__(ql)
  File "C:\Program Files\Python39\lib\site-packages\qiling\os\os.py", line 63, in __init__
    sys.stdin.fileno()
AttributeError: 'NoneType' object has no attribute 'fileno'
```

观察os.py的源码：

```python
try:
            # Qiling may be used on interactive shells (ex: IDLE) or embedded python
            # interpreters (ex: IDA Python). such environments use their own version
            # for the standard streams which usually do not support certain operations,
            # such as fileno(). here we use this to determine how we are going to use
            # the environment standard streams
            sys.stdin.fileno()
        except UnsupportedOperation:
            # Qiling is used on an interactive shell or embedded python interpreter.
            # if the internal stream buffer is accessible, we should use it
            self._stdin  = getattr(sys.stdin,  'buffer', sys.stdin)
            self._stdout = getattr(sys.stdout, 'buffer', sys.stdout)
            self._stderr = getattr(sys.stderr, 'buffer', sys.stderr)
```

报错提示sys.stdin为None，这是因为IDA修改了sys.stdin，使用了自己的输入输出流。这个问题在qiling的github issues，pull request都有提到，我这里直接捕获AttributeError异常，如下：

```python
except (UnsupportedOperation, AttributeError):
```

修复之后，重启IDA加载qiling环境（python安装的qiling环境），Qiling->Setup，报错如下：

> 这里修复的os.py文件是python库下的qiling，也就是C:\Program Files\Python39\lib\site-packages\qiling\os\os.py。

```
  File "E:\gitRepo\qiling\examples\extensions\idaplugin\custom_script.py", line 1, in <module>
    from future import __annotations__
ImportError: cannot import name '__annotations__' from 'future' (C:\Program Files\Python39\lib\site-packages\future\__init__.py)
[INFO][(unknown file):0] Custom user script not found.
```

这里我使用的python版本是3.9.13，大致查了一下，python库有\_\_future\_\_，没有future，不知道与python版本是否有关，改成如下形式，再次加载就成功了。

```python
from __future__ import annotations
```

### 开始模拟执行

现在，arm64_hello已加载进内存，动态链接器需要修复重定位表、设置程序入口点等，然后开始运行。

> > 阅读qiling\os\linux.py的QlOsLinux::run方法，由于当前是单线程环境，且没有显式指定运行的起始地址，因此程序的起始地址是动态链接器的入口点，待动态链接器初始化后，将跳转到程序的真正入口点：
> >
> > ```python
> >      try:
> >      	# 如果是一段二进制代码
> >          if self.ql.code:
> >              self.ql.emu_start(self.entry_point, (self.entry_point + len(self.ql.code)), self.ql.timeout, self.ql.count)
> >          else:
> >              # 如果是多线程环境
> >              if self.ql.multithread:
> >                  # start multithreading
> >                  thread_management = thread.QlLinuxThreadManagement(self.ql)
> >                  self.ql.os.thread_management = thread_management
> >                  thread_management.run()
> > 
> >              else:
> >                  # 不是多线程环境
> >                  # 程序入口点是否有显式指定
> >                  if self.ql.entry_point is not None:
> >                      self.ql.loader.elf_entry = self.ql.entry_point
> > 
> >                  # do we have an interp?
> >                  elif self.ql.loader.elf_entry != self.ql.loader.entry_point:
> >                      entry_address = self.ql.loader.elf_entry
> > 
> >                      if self.ql.arch.type == QL_ARCH.ARM:
> >                          entry_address &= ~1
> > 
> >                      # start running interp, but stop when elf entry point is reached
> >                      self.ql.emu_start(self.ql.loader.entry_point, entry_address, self.ql.timeout)
> >                      self.ql.do_lib_patch()
> >                      self.run_function_after_load()
> >                      self.ql.loader.skip_exit_check = False
> >                      self.ql.write_exit_trap()
> > 
> >                  self.ql.emu_start(self.ql.loader.elf_entry, self.exit_point, self.ql.timeout, self.ql.count)
> > ```

IDA汇编视图右键->Qiling Emulator->Continue开始模拟执行，报错：

```python
[+] 	brk: increasing program break from 0x555555568000 to 0x555555589000
[+] 	0x00007fffb7e9e93c: brk(inp = 0x555555589000) = 0x555555589000
[+] 	Received interrupt: 0x2
[+] 	write() CONTENT: b'Hello, World!\n'
[x] 	Syscall ERROR: ql_syscall_write DEBUG: A string expected
Traceback (most recent call last):
...
File "C:\Program Files\Python39\lib\site-packages\qiling\os\posix\syscall\unistd.py", line 410, in ql_syscall_write
    f.write(data)
  File "D:\Tools\IDA 7.5\python\3\init.py", line 63, in write
    ida_kernwin.msg(text)
  File "D:\Tools\IDA 7.5\python\3\ida_kernwin.py", line 236, in msg
    return _ida_kernwin.msg(*args)
TypeError: A string expected
```

这里看到已经成功执行puts函数，打印了“Hello, World”，当把这个字符串传给python打印时，出现异常，原因是qiling传给ida_kernwin.msg方法的类型是字节字符串，不是字符串。

解决办法有两个：

- 直接改D:\Tools\IDA 7.5\python\3\ida_kernwin.py的源码，兼容字节字符串
- hook write函数，替换掉qiling自己的ql_syscall_write

第一种方法由于是全局的，会影响到其他二进制文件的分析，且hook系统函数是qiling自身的功能，所以使用第二种方法。

修改custom_script.py，如下：

```python
def my_syscall_write(ql: Qiling, fd: int, buf: int, count: int):
    ql.log.info('my_syscall_write called')
    try:
        # read data from emulated memory
        data = ql.mem.read(buf, count)

        # select the emulated file object that corresponds to the requested
        # file descriptor
        fobj = ql.os.fd[fd]
        if fobj == None:
            ql.log.ingo('none file descriptor')
        # write the data into the file object, if it supports write operations
        elif hasattr(fobj, 'write'):
            fobj.write(data.decode('utf-8'))
    except:
        ret = -1
    else:
        ret = count

    ql.log.info(f'my_syscall_write({fd}, {buf:#x}, {count}) = {ret}')

    return ret
    
class QILING_IDA:

    def _show_context(self, ql: Qiling):
        registers = tuple(ql.arch.regs.register_mapping.keys())
        grouping = 4

        for idx in range(0, len(registers), grouping):
            ql.log.info('\t'.join(f'{r:5s}: {ql.arch.regs.read(r):016x}' for r in registers[idx:idx + grouping]))

    def custom_prepare(self, ql: Qiling) -> None:
        ql.log.info('Context before starting emulation:')
        ql.os.set_syscall('write', my_syscall_write)
        ql.log.info('my_syscall_write registered')
        self._show_context(ql)
```

这里实现了一个my_syscall_write函数，然后在QILING_IDA类的custom_prepare方法中调用ql.os.set_syscall来注册write的syscall。

修改custom_script后右键->Qiling Emulator->Reload User Scripts（后续简称Qiling菜单）就会重新加载脚本，最后在Qiling菜单点击`Restart`，重新开始运行，结果正常，打印出了“Hello, World!”。

```
[+] 	Received interrupt: 0x2
[=] 	my_syscall_write called
Hello, World!
[=] 	my_syscall_write(1, 0x555555568260, 14) = 14
[+] 	0x00007fffb7e98afc: my_syscall_write(fd = 0x1, buf = 0x555555568260, count = 0xe) = 0xe
[+] 	Received interrupt: 0x2
[+] 	0x00007fffb7e78a2c: exit_group(code = 0x0) = ?
```

### 通过显式设置PC寄存器指定程序执行入口

上节跑通了Qiling->Continue，现在尝试Qiling菜单的“设置运行地址”。

首先Qiling->Restart，在IDA里对__libc_start_main函数下断点，Qiling->Continue。此时会看到成功地断在了这里：

![image-20240717103851651](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240717103851651.png)

Qiling->View Register，查看PC寄存器，确认地址是否一致。这里发现PC的值是0x5E0+程序基址。

![image-20240717103902110](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240717103902110.png)

可以Qiling->Step，单步几次，会看到IDA中的不同颜色，这些颜色代表不同的执行操作。蓝色是单步，绿色的直接运行覆盖的路径。

![image-20240717103807022](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240717103807022.png)

sub_724函数是真正的打印函数，将光标移到sub_724的第一条指令，Qiling->Set PC，此时打印：

```
[INFO][(unknown file):0] QIling PC set to 0x724
```

看到设置好了PC后，继续Qiling->Continue，结果报错：

```
[x] 	CPU Context:
[x] 	x0	: 0x555555554724
[x] 	x1	: 0x1
[x] 	x2	: 0x80000000de18
...
[x] 	PC = 0x0000000000000724 (unreachable)
...
  File "C:\Program Files\Python39\lib\site-packages\qiling\core.py", line 771, in emu_start
    self.uc.emu_start(begin, end, timeout, count)
  File "C:\Program Files\Python39\lib\site-packages\unicorn\unicorn.py", line 547, in emu_start
    raise UcError(status)
unicorn.unicorn.UcError: Invalid memory fetch (UC_ERR_FETCH_UNMAPPED)
```

错误提示PC为0x724的代码是无法访问的，看寄存器：

![image-20240717104752266](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240717104752266.png)

这里的PC是0x724，回想之前看Qiling寄存器是 IDA地址 + 基址的形式，于是知道原因是Qiling->Set PC设置的是IDA地址，没有加上模块基址。

修改qiling的IDA插件,qilingida.py如下：

```python
    def ql_set_pc(self):
        if self.qlinit:
            # ea = IDA.get_current_address()
            ea = self.qlemu.ql_addr_from_ida(IDA.get_current_address())
            self.qlemu.ql.arch.regs.arch_pc = ea
            logging.info(f"QIling PC set to {hex(ea)}")
            self.qlemu.status = self.qlemu.ql.save()
            self.ql_update_views(self.qlemu.ql.arch.regs.arch_pc, self.qlemu.ql)
        else:
            logging.error('Qiling should be setup firstly.')
```

IDA插件更新后，先"Qiling->Unload Plugin"卸载插件，再IDA->File->Script file加载插件，然后重新操作一遍，这次设置PC就添上基址了：

```
[INFO][(unknown file):0] QIling PC set to 0x555555554724
```

最后，移动光标，点击sub_724的最后一条指令，然后Qiling->Execute Till，会看到这次成功执行，橙色代表Execute Till执行过的指令：

![image-20240717110923042](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240717110923042.png)

可以看到下一条指令就是0x748：

![image-20240717111000909](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240717111000909.png)

### 小节

从这里可以看到，qiling的IDA插件其实还不完善，即使是官方的dev分支（官方推荐使用dev分支），模拟执行demo还是有很多问题，所以对初学者不算非常友好。因此这里记录下相关问题的解决建议，供大家参考，后文还会有稍麻烦的bug需要解决。

## libxx.so的模拟执行（排错）

OK，demo已经跑通了，现在来模拟执行libxx.so。

![image-20240717111824127](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240717111824127.png)

可以看到算法的核心几个步骤是init，encrypt，decrypt。那么首先分析tps_init函数。

> 加载libxx.so、初始化qiling后，不能直接将PC寄存器指向tps_init函数，因为这时运行环境还没有准备好，比如tpidr_el0寄存器，这个寄存器类似与windows的fs段寄存器（TEB），指向当前线程的运行环境。另外，此时还没有做so的重定位，很多so里的全局引用是需要重定位的，比如调用一个memset函数。

首先IDA加载libxx.so，初始化qiling（Qiling->Setup），对libxx.so的入口地址（start函数）下断点，然后开始模拟执行（Qiling->Continue），报错：

```
[x] 	Syscall ERROR: ql_syscall_futex DEBUG: 'NoneType' object has no attribute 'cur_thread'
Traceback (most recent call last):
  File "C:\Program Files\Python39\lib\site-packages\qiling\os\posix\posix.py", line 374, in load_syscall
    retval = syscall_hook(self.ql, *params)
  File "C:\Program Files\Python39\lib\site-packages\qiling\os\posix\syscall\futex.py", line 43, in ql_syscall_futex
    regreturn = ql.os.futexm.futex_wake(ql, uaddr,ql.os.thread_management.cur_thread, val)
AttributeError: 'NoneType' object has no attribute 'cur_thread'
```

查看源码：

```python
elif op & (FUTEX_PRIVATE_FLAG - 1) == FUTEX_WAKE:
        regreturn = ql.os.futexm.futex_wake(ql, uaddr,ql.os.thread_management.cur_thread, val)
```

futex是linux中的锁，这里的thread_management是需要qiling启动多线程模式才会初始化的，于是在qilingida.py创建Qiling实例的时候添加多线程参数：

```python
class QlEmuQiling:
    def __init__(self):
        self.path = None
        self.rootfs = None
        self.ql: Qiling = None
        self.status = None
        self.exit_addr = None
        self.baseaddr = None
        self.env = {}

    def start(self, *args, **kwargs):
        self.ql = Qiling(argv=self.path, rootfs=self.rootfs, verbose=QL_VERBOSE.DEFAULT, multithread=True, env=self.env, log_plain=True, *args, **kwargs)
        # ...
```

这里日志打印从QL_VERBOSE.DEBUG改为QL_VERBOSE.DEFAULT，减少一些调试内容的输出，然后multithread显式打开。再卸载、加载一次qilingida.py，重新运行，以下报错：

```
[x] [Thread 2000]	Syscall ERROR: ql_syscall_writev DEBUG: A string expected
Traceback (most recent call last):
  File "C:\Program Files\Python39\lib\site-packages\qiling\os\posix\posix.py", line 374, in load_syscall
    retval = syscall_hook(self.ql, *params)
  File "C:\Program Files\Python39\lib\site-packages\qiling\os\posix\syscall\uio.py", line 23, in ql_syscall_writev
    ql.os.fd[fd].write(buf)
  File "D:\Tools\IDA 7.5\python\3\init.py", line 63, in write
    ida_kernwin.msg(text)
  File "D:\Tools\IDA 7.5\python\3\ida_kernwin.py", line 236, in msg
    return _ida_kernwin.msg(*args)
TypeError: A string expected
```

这个和之前demo的问题一样，只是这次的syscall是writev，不是write。在custom_script.py添加writev的syscall hook，定义my_syscall_writev函数，Qiling->Reload User Script重新加载自定义脚本，重启qiling环境运行，这次成功运行到start函数：

![image-20240717140048966](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240717140048966.png)

但注意tpidr_el0为0，代表线程运行环境没有准备好。如果这时直接Qiling->continue，还会出现另一个报错：

```
[x] [Thread 2000]	PC = 0x000000000009aec0 (unreachable)
[x] [Thread 2000]	Memory map:
[x] [Thread 2000]	Start            End              Perm    Label        Image
[x] [Thread 2000]	00555555554000 - 00555555847000   r-x     libxx.so     E:\gitRepo\qiling\examples\rootfs\arm64_linux\bin\libxx.so
[x] [Thread 2000]	00555555856000 - 0055555588f000   rw-     libxx.so     E:\gitRepo\qiling\examples\rootfs\arm64_linux\bin\libxx.so
[x] [Thread 2000]	0055555588f000 - 00555555891000   rwx     [hook_mem]   
[x] [Thread 2000]	007ffffffde000 - 0080000000e000   rwx     [stack]      
Traceback (most recent call last):
...
  File "C:\Program Files\Python39\lib\site-packages\unicorn\unicorn.py", line 547, in emu_start
    raise UcError(status)
unicorn.unicorn.UcError: Invalid memory fetch (UC_ERR_FETCH_UNMAPPED)
```

这里可以看到，PC准备执行0x9aec0处的指令，但从打印的内存映射来看，0x9aec0是没有映射的，所以导致指令读取失败。

再更仔细地看内存映射信息，发现没有动态链接器加载到内存空间，用readelf看一下：

```
$ readelf -S libxx.so | grep interp
---
$ readelf -S arm64_hello | grep interp
  [ 1] .interp           PROGBITS         0000000000000200  00000200
```

libxx.so没有interp节，而arm64_hello有，所以qiling在加载libxx.so的时候没有加载动态链接器。

那现在需要给libxx.so显示指定动态链接器，为确定在哪指定，先打开debug级别的日志输出：

```
    def start(self, *args, **kwargs):
        self.ql = Qiling(argv=self.path, rootfs=self.rootfs, verbose=QL_VERBOSE.DEBUG, multithread=True, env=self.env, log_plain=True, *args, **kwargs)
```

重新加载qilingida.py，初始化qiling环境，结果没有相关输出。再用IDA打开arm64_hello，相关输出如下：

```
[INFO][qilingida:1034] Custom env: {}
[+] 	Profile: default
[+] 	Mapped 0x555555554000-0x555555555000
[+] 	Mapped 0x555555564000-0x555555566000
[+] 	mem_start : 0x555555554000
[+] 	mem_end   : 0x555555566000
[+] 	Interpreter path: /lib/ld-linux-aarch64.so.1
[+] 	Interpreter addr: 0x7ffff7dd5000
[+] 	Mapped 0x7ffff7dd5000-0x7ffff7df2000
[+] 	Mapped 0x7ffff7e01000-0x7ffff7e04000
[+] 	mmap_address is : 0x7fffb7dd6000
```

看到arm64_hello的动态链接器是/lib/ld-linux-aarch64.so.1，根据这个打印日志，去qiling源码查找：

```python
def load_with_ld()
	def load_elf_segments()
    	# ...
        # determine interpreter path
        interp_seg = next(elffile.iter_segments(type='PT_INTERP'), None)
        interp_path = str(interp_seg.get_interp_name()) if interp_seg else ''
```

这里的interp_path为动态链接器的路径，所以显示指定如下：

```python
        if len(interp_path) == 0:
            interp_path = "/lib/ld-linux-aarch64.so.1"
```

重启qiling环境，可看到动态链接器的加载：

```
[INFO][qilingida:1034] Custom env: {}
[+] 	Profile: default
[+] 	Mapped 0x555555554000-0x555555847000
[+] 	Mapped 0x555555856000-0x55555588f000
[+] 	mem_start : 0x555555554000
[+] 	mem_end   : 0x55555588f000
[+] 	Interpreter path: /lib/ld-linux-aarch64.so.1
[+] 	Interpreter addr: 0x7ffff7dd5000
[+] 	Mapped 0x7ffff7dd5000-0x7ffff7df2000
[+] 	Mapped 0x7ffff7e01000-0x7ffff7e04000
```

然后开始qiling的模拟执行（Qiling->Continue），如下报错：

```
[+] [Thread 2000]	b'Inconsistency detected by ld.so: '
Inconsistency detected by ld.so: [+] [Thread 2000]	b'rtld.c'
rtld.c[+] [Thread 2000]	b': '
: [+] [Thread 2000]	b'1266'
1266[+] [Thread 2000]	b': '
: [+] [Thread 2000]	b'dl_main'
dl_main[+] [Thread 2000]	b': '
: [+] [Thread 2000]	b'Assertion `'
Assertion `[+] [Thread 2000]	b'GL(dl_rtld_map).l_libname'
GL(dl_rtld_map).l_libname[+] [Thread 2000]	b"' failed!\n"
' failed!
...
  File "C:\Program Files\Python39\lib\site-packages\qiling\os\linux\linux.py", line 167, in run
    thread_management.run()
  File "C:\Program Files\Python39\lib\site-packages\qiling\os\linux\thread.py", line 613, in run
    previous_thread = self._prepare_lib_patch()
  File "C:\Program Files\Python39\lib\site-packages\qiling\os\linux\thread.py", line 593, in _prepare_lib_patch
    raise QlErrorExecutionStop('Dynamic library .init() failed!')
qiling.exception.QlErrorExecutionStop: Dynamic library .init() failed!
```

第一句话直接提示了该动态链接器不兼容当前so。想起这个so是通过ndk编译给安卓用的，那动态链接器应该是安卓下的linker64。

Bet4从qiling的github fork了仓库，里面有linker64和安卓下所需的其他so，比如libz、libm、liblog。

用readelf看到libxx.so引用了这些库，所以这里一并准备好，路径如下：

```
$ readelf -d libxx.so

Dynamic section at offset 0x311f88 contains 29 entries:
  Tag        Type                         Name/Value
 0x0000000000000001 (NEEDED)             Shared library: [liblog.so]
 0x0000000000000001 (NEEDED)             Shared library: [libz.so]
 0x0000000000000001 (NEEDED)             Shared library: [libm.so]
 0x0000000000000001 (NEEDED)             Shared library: [libdl.so]
 0x0000000000000001 (NEEDED)             Shared library: [libc.so]
 0x000000000000000e (SONAME)             Library soname: [libtps.so]
 0x0000000000000019 (INIT_ARRAY)         0x302dc0
 0x000000000000001b (INIT_ARRAYSZ)       8 (bytes)
 0x000000000000001a (FINI_ARRAY)         0x302dc8
 ...
```

```
E:\gitRepo\qiling\examples\rootfs\arm64_linux\system\lib64：保存libm.so等库
E:\gitRepo\qiling\examples\rootfs\arm64_linux\lib：保存linker64
```

该动态链接器更换为linker64后，重启IDA，初始化qiling环境，Qiling->Continue，出现以下报错：

```
[x] [Thread 2000]	Disassembly:
[=] [Thread 2000]	00007ffff7ddfbd0 [linker64             + 0x00abd0]  9c 20 40 79          ldrh                 w28, [x4, #0x10]
[=] [Thread 2000]	00007ffff7ddfbd4 [linker64             + 0x00abd4]  9f 0f 00 71          cmp                  w28, #3
[=] [Thread 2000]	00007ffff7ddfbd8 [linker64             + 0x00abd8]  81 34 00 54          b.ne                 #0x7ffff7de0268
...
  File "C:\Program Files\Python39\lib\site-packages\qiling\core.py", line 771, in emu_start
    self.uc.emu_start(begin, end, timeout, count)
  File "C:\Program Files\Python39\lib\site-packages\unicorn\unicorn.py", line 547, in emu_start
    raise UcError(status)
unicorn.unicorn.UcError: Invalid memory read (UC_ERR_READ_UNMAPPED)
```

此时X4为0，导致了内存访问异常。用IDA打开linker64，崩溃点如下：

![image-20240717150000658](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240717150000658.png)

大致看了上下文，该函数是\_dl\_\_\_linker\_init，用来初始化动态库so，要知道X4为什么是0还得往上回溯，需要一点时间。且这个linker64是安卓低版本6.0，可能有不兼容的地方，于是我想尝试另外的linker64，正好手上有一台PIXEL，于是把里面的linker64复制出来，再测试一次，结果如下：

```
[+] [Thread 2001]	b'libc'
libc[+] [Thread 2001]	b': '
: [+] [Thread 2001]	b'unable to stat "/proc/self/exe": Operation not permitted'
unable to stat "/proc/self/exe": Operation not permitted[+] [Thread 2001]	b'\n'
```

报错无法读取/proc/self/exe，这是一个符号链接，linker64用它来获取自身的绝对路径，linker伪代码如下：

![image-20240717210638992](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240717210638992.png)

这里用qiling hook 0x27DA8地址，然后返回绝对路径和长度，更新custom_script.py:

```python
def custom_continue(self, ql: Qiling) -> List[HookRet]:
    # ...
    def addr_27DA8_hook(ql: Qiling) -> None:
        ql.arch.regs.W0 = 0
        ql.arch.regs.PC += 4
    # ...
    return [ql.hook_address(addr_27DA8_hook, 0x27DA8+linker_baseaddr)]
```

重新来一遍，又来一个报错：

```
[+] [Thread 2000]	b'libc'
libc[+] [Thread 2000]	b': '
: [+] [Thread 2000]	b'Could not find a PHDR: broken executable?'
Could not find a PHDR: broken executable?[+] [Thread 2000]	b'\n'
```

这里找不到 PHDR 程序头表，用readelf看一下：

```
$ readelf -l libxx.so

Elf file type is DYN (Shared object file)
Entry point 0xa5370
There are 8 program headers, starting at offset 64

Program Headers:
  Type           Offset             VirtAddr           PhysAddr
                 FileSiz            MemSiz              Flags  Align
  LOAD           0x0000000000000000 0x0000000000000000 0x0000000000000000
                 0x00000000002f25b4 0x00000000002f25b4  R E    0x10000
  LOAD           0x00000000002f2dc0 0x0000000000302dc0 0x0000000000302dc0
                 0x0000000000034478 0x0000000000037d58  RW     0x10000
  DYNAMIC        0x0000000000311f88 0x0000000000321f88 0x0000000000321f88
                 0x0000000000000210 0x0000000000000210  RW     0x8
  NOTE           0x0000000000000200 0x0000000000000200 0x0000000000000200
                 0x0000000000000024 0x0000000000000024  R      0x4
  NOTE           0x00000000002f251c 0x00000000002f251c 0x00000000002f251c
                 0x0000000000000098 0x0000000000000098  R      0x4
  GNU_EH_FRAME   0x00000000002da5dc 0x00000000002da5dc 0x00000000002da5dc
                 0x000000000000355c 0x000000000000355c  R      0x4
  GNU_STACK      0x0000000000000000 0x0000000000000000 0x0000000000000000
                 0x0000000000000000 0x0000000000000000  RW     0x10
  GNU_RELRO      0x00000000002f2dc0 0x0000000000302dc0 0x0000000000302dc0
                 0x0000000000025240 0x0000000000025240  R      0x1
```

一般PHDR是程序表(program table)的第一个元素，这里确实没有。看一下IDA：

![image-20240717213805454](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240717213805454.png)

这里也出现了一个变量+0x10的判断，对比Bet4的linker64上下文和PIXEL的linker64上下文，可确定是同一个问题，看来必须要往上逆向一下了。

> 图的注释是分析后的结果。

这里有两种方式，一种是打trace，即使用Qiling的hook_code，在每一条代码运行前打印现场环境，一种是断在对应的代码，单步做动态调试，这里我选择动态调试的方式。那如何断在对应的代码地址呢，这里要熟悉下qilingida.py的这部分代码：

```python
def ql_continue(self):
    logging.info("before continue...")
    if self.qlinit:
        userhook = None
        # 调用hook_code，每条指令执行前调用ql_path_hook
        pathhook = self.qlemu.ql.hook_code(self.ql_path_hook)

def ql_path_hook(self, ql, addr, size):
    addr = addr - self.qlemu.baseaddr + get_imagebase()
    set_color(addr, CIC_ITEM, 0x007FFFAA)
    # 获取断点数量
    bp_count = get_bpt_qty()
    bp_list = []
    if bp_count > 0:
        for num in range(0, bp_count):
            bp_list.append(get_bpt_ea(num))

        # 如果当前准备执行的指令是断点处的指令，调用ql.save和ql.os.stop()保存当前模拟执行环境
        if addr in bp_list and (addr != self.lastaddr or self.is_change_addr>1):
            self.qlemu.status = ql.save()
            ql.os.stop()
            self.lastaddr = addr
            self.is_change_addr = -1
            jumpto(addr)

        self.is_change_addr += 1
```

这部分代码表示让模拟执行跑起来时，如果遇到断点，就保存现场环境并停下来，所以断在想分析的代码地址处可以在ql_path_hook手动加一个断点，如下：

```python
def ql_path_hook(self, ql, addr, size):
    addr = addr - self.qlemu.baseaddr + get_imagebase()
    set_color(addr, CIC_ITEM, 0x007FFFAA)
    bp_count = get_bpt_qty() + 1
    bp_list = []
    bp_list.append(0x27f2c+0x007ffff7dd5000-0x555555554000)
    if bp_count > 0:
        for num in range(0, bp_count):
            bp_list.append(get_bpt_ea(num))
```

这里给bp_list加一个元素，0x27f2c为相对虚拟地址(RVA)，后面是重定位的基址调整，这样就能断下来，然后单步调试了。

> - 因为第二行addr变量重定位时减去的libxx模块的基址，所以bp_list添加的元素要减去libxx模块的基址，而不是0x27f2c+0x007ffff7dd5000-0x007ffff7dd5000=0x27f2c。
>
> - 因为中断后，PC寄存器指向linker64模块，所以会报以下错误，不过该错误不影响继续单步调试：
>
>   ```
>   [x] [Thread 2000]	[Thread 2000] Expect 0x5555555f9370 but get 0x7ffff7e9e920 when running loader.
>   Traceback (most recent call last):
>   ...
>     File "C:\Program Files\Python39\lib\site-packages\qiling\os\linux\linux.py", line 167, in run
>       thread_management.run()
>     File "C:\Program Files\Python39\lib\site-packages\qiling\os\linux\thread.py", line 613, in run
>       previous_thread = self._prepare_lib_patch()
>     File "C:\Program Files\Python39\lib\site-packages\qiling\os\linux\thread.py", line 593, in _prepare_lib_patch
>       raise QlErrorExecutionStop('Dynamic library .init() failed!')
>   qiling.exception.QlErrorExecutionStop: Dynamic library .init() failed!
>   ```

单步调试后，伪代码如下：

```cpp
i = 0;
while (program_table_element[i].p_type!=PT_PHDR) {
	i++;
    if (i >= elf_header.e_phnum)
        break;
}

if (i == elf_header.e_phnum) {
    print("no phdr");
}
else {
    // 获取文件基址在内存的地址
    a = phdr_addr - program_table_element[i].p_paddr;
    // 获取内存基址
    b = phdr_addr - program_table_elemet[i].p_offset;
}
```

这里可以模拟程序头表获取变量a和变量b，修改custom_script.py如下：

```python
def custom_continue(self, ql: Qiling) -> List[HookRet]:
	#...
	def addr_27FB4_hook(ql: Qiling) -> None:
        	# 如果是检测第一个程序表元素，且不是程序头表
            if ql.arch.regs.X11 == 0 and ql.arch.regs.W12 == 1:
                phdr_vir_addr = ql.arch.regs.X8
                poffset_addr = ql.arch.regs.x10
                write_base = ql.arch.regs.X19
                ql.log.info(f'phdr_vir_addr: {phdr_vir_addr:#x}')
                ql.log.info(f'poffset_addr: {poffset_addr:#x}')
                sub1 = to_bstring(phdr_vir_addr-0x40)
                # *(QWORD*)((__int64)v50+0x100) = image_vir_addr
                ql.mem.write(write_base+0x100, sub1)
                ql.log.info(b'sub1: ' + sub1)

                image_vir_addr = phdr_vir_addr-0x40
                # *(QWORD*)((__int64)v50+0x10) = image_vir_addr
                ql.mem.write(write_base+0x10, to_bstring(0x40))
                ql.log.info(f'sub2: {image_vir_addr:#x}')

                ql.arch.regs.X8 = image_vir_addr
                ql.arch.regs.PC = 0x28070 + 0x7ffff7dd5000
                
	ql.hook_address(addr_27FB4_hook, 0x27FB4+linker_baseaddr)
```

> 记得把之前在qilingida.py添加的断点去掉。

重启qiling环境，这样就能够断在libxx.so的start地址处了。

遗憾的是，到这里仍然不能顺利模拟执行我们的目标函数，因为qiling模拟执行到start大约需要3-4分钟，如果每次分析调整完qiling代码后，都重启一次qiling，那这个效率就太低了。

写这篇文章的时候，为了演示，我重新又走了一遍流程，结果这次直接卡死了，IDA一直消耗CPU一整晚，到白天都还没有弄完：

![image-20240724102141265](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240724102141265.png)

经过分析，发现通过Qiling->Continue的方式，每执行一条执行都会调用设置的callback（qilingida.py->ql_path_hook），如果取消这个回调注册，qiling就会大约2-3秒来到start地址处。

重启qiling环境，这次遇到了这个错误：

```
[x] [Thread 2000]	v28	: 0x0
[x] [Thread 2000]	v29	: 0x0
[x] [Thread 2000]	v30	: 0x0
[x] [Thread 2000]	v31	: 0x0
[x] [Thread 2000]	PC = 0x0000000000000000 (unreachable)

[x] [Thread 2000]	Memory map:
[x] [Thread 2000]	Start            End              Perm    Label              Image
[x] [Thread 2000]	00555555554000 - 00555555847000   r-x     libxx.so           E:\gitRepo\qiling\examples\rootfs\arm64_linux\bin\libxx.so
[x] [Thread 2000]	00555555856000 - 0055555587c000   r--     libxx.so           E:\gitRepo\qiling\examples\rootfs\arm64_linux\bin\libxx.so
[x] [Thread 2000]	0055555587c000 - 0055555588f000   rw-     libxx.so           E:\gitRepo\qiling\examples\rootfs\arm64_linux\bin\libxx.so
[x] [Thread 2000]	0055555588f000 - 00555555891000   rwx     [hook_mem]         
[x] [Thread 2000]	007fffb7dd6000 - 007fffb7dd7000   ---     [mmap anonymous]   
[x] [Thread 2000]	007fffb7dd7000 - 007fffb7dda000   rw-     [mmap anonymous]   
[x] [Thread 2000]	007fffb7dda000 - 007fffb7ddb000   ---     [mmap anonymous]   
[x] [Thread 2000]	007fffb7ddb000 - 007fffb7ddc000   ---     [mmap anonymous]   
[x] [Thread 2000]	007fffb7ddc000 - 007fffb7de0000   rw-     [mmap anonymous]   
[x] [Thread 2000]	007fffb7de0000 - 007fffb7de1000   r--     [mmap anonymous]   
[x] [Thread 2000]	007fffb7de1000 - 007fffb7de2000   rw-     [mmap anonymous]   
[x] [Thread 2000]	007fffb7de2000 - 007fffb7de3000   rw-     [mmap anonymous]   
[x] [Thread 2000]	007fffb7de3000 - 007fffb7de4000   rw-     [mmap anonymous]   
[x] [Thread 2000]	007fffb7de5000 - 007fffb7de6000   rw-     [mmap anonymous]   
[x] [Thread 2000]	007fffb7de6000 - 007fffb7de7000   r--     [mmap anonymous]   
[x] [Thread 2000]	007fffb7de7000 - 007fffb7de8000   ---     [mmap anonymous]   
[x] [Thread 2000]	007fffb7de8000 - 007fffb7de9000   rw-     [mmap anonymous]   
[x] [Thread 2000]	007fffb7de9000 - 007fffb7dea000   ---     [mmap anonymous]   
[x] [Thread 2000]	007fffb7dea000 - 007fffb7deb000   r--     [mmap anonymous]   
[x] [Thread 2000]	007fffb7deb000 - 007fffb7dec000   rw-     [mmap anonymous]   
[x] [Thread 2000]	007fffb7dec000 - 007fffb7ded000   rw-     [mmap anonymous]   
[x] [Thread 2000]	007fffb7ded000 - 007fffb7dee000   rw-     [mmap anonymous]   
[x] [Thread 2000]	007fffb7dee000 - 007fffb7def000   rw-     [mmap anonymous]   
[x] [Thread 2000]	007fffb7def000 - 007fffb7df0000   rw-     [mmap anonymous]   
[x] [Thread 2000]	007fffb7df0000 - 007fffb7df1000   r--     [mmap anonymous]   
[x] [Thread 2000]	007fffb7df1000 - 007fffb7df2000   rw-     [mmap anonymous]   
[x] [Thread 2000]	007fffb7e31000 - 007fffb7e32000   rw-     [mmap anonymous]   
[x] [Thread 2000]	007fffb7e32000 - 007fffb7e33000   rw-     [mmap anonymous]   
[x] [Thread 2000]	007fffb7e4b000 - 007fffb7f0e000   r-x     [mmap] libc.so     
[x] [Thread 2000]	007fffb7f0e000 - 007fffb7f1d000   ---     [mmap anonymous]   
[x] [Thread 2000]	007fffb7f1d000 - 007fffb7f23000   r--     [mmap] libc.so     
[x] [Thread 2000]	007fffb7f23000 - 007fffb7f26000   rw-     [mmap] libc.so     
[x] [Thread 2000]	007fffb7f26000 - 007fffb7f34000   rw-     [mmap anonymous]   
[x] [Thread 2000]	007fffb7f5d000 - 007fffb7f5e000   r-x     [mmap] libdl.so    
[x] [Thread 2000]	007fffb7f5e000 - 007fffb7f6d000   ---     [mmap anonymous]   
[x] [Thread 2000]	007fffb7f6d000 - 007fffb7f6e000   r--     [mmap] libdl.so    
[x] [Thread 2000]	007fffb7f6e000 - 007fffb7f6f000   rw-     [mmap] libdl.so    
[x] [Thread 2000]	007fffb7f81000 - 007fffb8058000   r-x     [mmap] libc++.so   
[x] [Thread 2000]	007fffb8058000 - 007fffb8067000   ---     [mmap anonymous]   
[x] [Thread 2000]	007fffb8067000 - 007fffb806e000   r--     [mmap] libc++.so   
[x] [Thread 2000]	007fffb806e000 - 007fffb806f000   rw-     [mmap] libc++.so   
[x] [Thread 2000]	007fffb806f000 - 007fffb8072000   rw-     [mmap anonymous]   
[x] [Thread 2000]	007fffb80b5000 - 007fffb80ed000   r-x     [mmap] libm.so     
[x] [Thread 2000]	007fffb80ed000 - 007fffb80fd000   ---     [mmap anonymous]   
[x] [Thread 2000]	007fffb80fd000 - 007fffb80fe000   r--     [mmap] libm.so     
[x] [Thread 2000]	007fffb80fe000 - 007fffb80ff000   rw-     [mmap] libm.so     
[x] [Thread 2000]	007fffb8106000 - 007fffb8122000   r-x     [mmap] libz.so     
[x] [Thread 2000]	007fffb8122000 - 007fffb8131000   ---     [mmap anonymous]   
[x] [Thread 2000]	007fffb8131000 - 007fffb8132000   r--     [mmap] libz.so     
[x] [Thread 2000]	007fffb8132000 - 007fffb8133000   rw-     [mmap] libz.so     
[x] [Thread 2000]	007fffb8160000 - 007fffb8165000   r-x     [mmap] liblog.so   
[x] [Thread 2000]	007fffb8165000 - 007fffb8174000   ---     [mmap anonymous]   
[x] [Thread 2000]	007fffb8174000 - 007fffb8175000   r--     [mmap] liblog.so   
[x] [Thread 2000]	007fffb8175000 - 007fffb8176000   rw-     [mmap] liblog.so   
...
  File "C:\Program Files\Python39\lib\site-packages\qiling\core.py", line 771, in emu_start
    self.uc.emu_start(begin, end, timeout, count)
  File "C:\Program Files\Python39\lib\site-packages\unicorn\unicorn.py", line 547, in emu_start
    raise UcError(status)
unicorn.unicorn.UcError: Invalid memory fetch (UC_ERR_FETCH_UNMAPPED)
```

这里PC跳到了0x0，不过我们可以看到libxx.so需要的依赖库都被完美地加载到内存了，说明动态链接器加载libxx.so应该是完成了。

因为取消了ql_path_hook的回调，所以不能断到断点处，所以得另外用一种方法断到start地址处。

qiling有一个“运行到”的函数，右键是Qiling->Execute Till，观察qiling的IDA插件：

```python
def ql_run_to_here(self):
    if self.qlinit:
        curr_addr = get_screen_ea()
        # 每执行一条命令前，调用ql_until_hook
        untillhook = self.qlemu.ql.hook_code(self.ql_untill_hook)
        if self.qlemu.status is not None:
            self.qlemu.ql.restore(self.qlemu.status)
            show_wait_box("Qiling is processing ...")
            try:
                self.qlemu.run(begin=self.qlemu.ql.arch.regs.arch_pc, end=curr_addr+self.qlemu.baseaddr-get_imagebase())
            finally:
                hide_wait_box()
        else:
            show_wait_box("Qiling is processing ...")
            try:
                self.qlemu.run(end=curr_addr+self.qlemu.baseaddr-get_imagebase())
            finally:
                hide_wait_box()
```

qiling在run方法中提供了end，代表模拟执行在哪里结束。我们可以把end设置为start地址就相当于断在start上了，通过在IDA将光标移到对应的代码处即可设置end。不过这里也有一个指令集回调（第4行），观察ql_until_hook的实现：

```python
def ql_untill_hook(self, ql, addr, size):
    addr = addr - self.qlemu.baseaddr + get_imagebase()
    set_color(addr, CIC_ITEM, 0x00B3CBFF)
```

该函数只是将模拟执行过的代码设置高亮，因此我们可以直接注视掉这个回调的注册（在ql_run_to_here去掉对ql_until_hook的hook_code和hook_del调用）。另外，之前在custom_continue设置的回调都要copy一份到custom_run_to_here，custom_script.py没有该函数就创建一个：

qilingida.py:

```python
def ql_run_to_here(self):
    if self.qlinit:
        curr_addr = get_screen_ea()
        userhook = None
        # 注册新创建的custom_run_to_here方法
        if self.userobj is not None:
            userhook = self.userobj.custom_run_to_here(self.qlemu.ql)
        # 去掉ql_until_hook的回调
        # untillhook = self.qlemu.ql.hook_code(self.ql_untill_hook)
        if self.qlemu.status is not None:
            self.qlemu.ql.restore(self.qlemu.status)
            show_wait_box("Qiling is processing ...")
            try:
                self.qlemu.run(begin=self.qlemu.ql.arch.regs.arch_pc, end=curr_addr+self.qlemu.baseaddr-get_imagebase())
            finally:
                hide_wait_box()
        else:
            show_wait_box("Qiling is processing ...")
            try:
                self.qlemu.run(end=curr_addr+self.qlemu.baseaddr-get_imagebase())
            finally:
                hide_wait_box()

        set_color(curr_addr, CIC_ITEM, 0x00B3CBFF)
        # 回调删除部分也注视掉
        # self.qlemu.ql.hook_del(untillhook)
        if userhook and userhook is not None:
            for hook in userhook:
                self.qlemu.ql.hook_del(hook)
        self.qlemu.status = self.qlemu.ql.save()
        self.ql_update_views(self.qlemu.ql.arch.regs.arch_pc, self.qlemu.ql)
    else:
        logging.error('Qiling should be setup firstly.')
```

custom_script.py:

```python
def custom_run_to_here(self, ql: Qiling) -> List[HookRet]:

    linker_baseaddr = 0x007ffff7dd5000

    def addr_27DA8_hook(ql: Qiling) -> None:
		# content from ql_continue

    def addr_27FB4_hook(ql: Qiling) -> None:
        # content from ql_continue

    return [ql.hook_address(addr_27DA8_hook, 0x27DA8+linker_baseaddr),
            ql.hook_address(addr_27FB4_hook, 0x27FB4+linker_baseaddr)]
```

OK，输出终于没有报错了，观察寄存器，也顺利执行到了start地址处：

![image-20240724163047823](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240724163047823.png)

修改之后，重启qiling环境，将光标移到start代码处，右键Qiling->Execute Till。

接下来就是单步执行了，结果遇到如下问题：

```
[=] [Thread 2000]	custom_step hook
[=] [Thread 2001]	Executing: 0x7ffff7e0373c
[x] [Thread 2001]	[Thread 2001] Expect 0x5555555f9370 but get 0x7ffff7e03740 when running loader.
  File "C:\Program Files\Python39\lib\site-packages\qiling\os\linux\thread.py", line 611, in run
    previous_thread = self._prepare_lib_patch()
  File "C:\Program Files\Python39\lib\site-packages\qiling\os\linux\thread.py", line 590, in _prepare_lib_patch
    raise QlErrorExecutionStop('Dynamic library .init() failed!')
qiling.exception.QlErrorExecutionStop: Dynamic library .init() failed!
```

这里显示单步执行的命令地址是0x7ffff7e0373c，而不是0x5555555f9370。要定位这个问题需要了解qiling源码，分析流程如下：

```python
# qilingida,py
# 单步执行的入口是qlemu.run
def ql_step(self):
    self.qlemu.run(begin=self.qlemu.ql.arch.regs.arch_pc, end=self.qlemu.exit_addr)
    
# qiling/os/linux/linux.py
class QlOsLinux(QlOsPosix):
    def run(self):
        # 多线程环境下调用thread_management.run()
        if self.ql.multithread:
            # start multithreading
            thread_management = thread.QlLinuxThreadManagement(self.ql)
            self.ql.os.thread_management = thread_management
            thread_management.run()
        else:
            # 单线程环境
            if self.ql.entry_point is not None:
                self.ql.loader.elf_entry = self.ql.entry_point

            # do we have an interp?
            # 如果有动态链接器，就用动态链接器初始化目标so
            elif self.ql.loader.elf_entry != self.ql.loader.entry_point:
                entry_address = self.ql.loader.elf_entry

                if self.ql.arch.type == QL_ARCH.ARM:
                    entry_address &= ~1

                # start running interp, but stop when elf entry point is reached
                self.ql.emu_start(self.ql.loader.entry_point, entry_address, self.ql.timeout)
            
            # 开始模拟执行目标so
            self.ql.emu_start(self.ql.loader.elf_entry, self.exit_point, self.ql.timeout, self.ql.count)
        
# qiling/os/linux/thread.py
class QlLinuxThreadManagement:
    def run(self):
        # 调用_prepare_lib_patch，让动态链接器加载目标libxx.so
        previous_thread = self._prepare_lib_patch()
        
    def _prepare_lib_patch(self):
        # 如果动态加载器的入口点不等于目标libxx.so的入口点，就初始化libxx.so
        # 这个判断的逻辑就是目标libxx.so如果是第一次加载，就用动态链接器加载，做重定位之类的，
        # 如果不是第一次加载，就直接返回None，继续执行，即不做重定位等。
		if self.ql.loader.elf_entry != self.ql.loader.entry_point:
            entry_address = self.ql.loader.elf_entry

            if self.ql.arch.type == QL_ARCH.ARM:
                entry_address &= ~1

            self.main_thread = self.ql.os.thread_class.spawn(self.ql, self.ql.loader.entry_point, entry_address)
            self.cur_thread = self.main_thread
            self._clear_queued_msg()
            gevent.joinall([self.main_thread], raise_error=True)
            if self.ql.arch.regs.arch_pc != entry_address:
                self.ql.log.error(f"{self.cur_thread} Expect {hex(self.ql.loader.elf_entry)} but get {hex(self.ql.arch.regs.arch_pc)} when running loader.")
                raise QlErrorExecutionStop('Dynamic library .init() failed!')
            self.ql.do_lib_patch()
            self.ql.os.run_function_after_load()
            self.ql.loader.skip_exit_check = False
            self.ql.write_exit_trap()
            return self.main_thread
        return None
```

观察代码流程，我们发现单线程环境下，如果指定了ql.entry_point（调用ql.run的begin参数），就不会重定位，直接开始模拟执行。这是正常的，因为第一次模拟执行时我们一般不会指定ql.run的begin参数，而是让动态链接器去初始化so，不过我们会注册一些回调，使得之后可以保存快照和恢复模拟执行，而恢复模拟执行就会设置ql.run的begin参数。在看多线程的环境，qiling官方显然没有考虑到这个，每次调用ql.run都会执行\_prepare\_lib\_path，用动态链接器初始化so。在我们的场景下，我们已经初始化过libxx.so，且想要开始单步调试so，而由于qiling又一次初始化libxx.so，所以单步调试后的下一条指令是动态加载器的入口地址+4，而不是libxx.so的入口地址+4。

这里直接模仿单线程环境，修改如下：

```python
# qiling/os/linux/thread.py

def _prepare_lib_patch(self):
    if self.ql.entry_point is not None:
        self.ql.loader.elf_entry = self.ql.entry_point
        return None
    elif self.ql.loader.elf_entry != self.ql.loader.entry_point:
        entry_address = self.ql.loader.elf_entry
```

这里添加一个ql.entry_point的判断，如果ql.run设置了begin，就不重定位，直接从begin地址处开始模拟执行。

重启qiling环境，再次执行Qiling->Execute Till：

![image-20240725103246929](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240725103246929.png)

可以看到，这次单步调试成功了，顺利在断在了libxx.so的下一条指令。

继续单步执行，进入".\_\_cxa\_finalize"函数，该函数是从内存读取__cxa_finalize真正的函数地址并执行，该函数地址是需要重定位的，因为该函数属于其他模块，我们观察其内存：

![image-20240725103947132](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240725103947132.png)

__cxa_finalize_ptr是保存函数地址的指针，通过IDA View-B可看到其相对虚拟地址是0x3266D0，X16寄存器保存了\_\_cxa_finalize_ptr所在的内存页，我们查看内存，发现0x6D0偏移处是0x7FFFB80F942C，该地址位于libc.so中，所以由此得知动态链接器正确地完成了libxx.so的重定位。

```
[x] [Thread 2000]	007fffb8085000 - 007fffb8148000   r-x     [mmap] libc.so
```

## 虚拟机框架解析

libxx.so有3个重要的接口：

- tps_init：tps_init初始化和收集环境信息，发送给服务器
- tps_encrypt、tps_decrypt：负责数据的加解密

因为tps_init与算法无关，这里就直接忽略了。

先看下加解密函数的伪代码：

![image-20240725105318159](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240725105318159.png)

![image-20240725105333731](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240725105333731.png)

两个函数结构一致，sub_F736C是真正的加解密函数，加密与解密的不同在于sub_F736C的第1、3、4参数。

### 虚拟机的简要流程

回顾sub_F736C的整体结构：

![image-20240725105747850](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240725105747850.png)

感觉像是几层嵌套的控制流平坦化，通过单步模拟执行，其实际上是一个虚拟机的简化版，这里简要说明其流程：

- 初始化一些计算因子，然后进入while(1)无限循环，v66从a1参数读取一个四字节大小的无符号整形，然后与0x3F做&算法，最后传给switch

  > 这里IDA反编译出现了一点问题，传给switch的不是v39

  ![image-20240725134708083](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240725134708083.png)

- 一个大switch

  ![image-20240725110152019](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240725110152019.png)

- 假如v39是0x9，跳到对应的case，执行[vmstack-off1] = [vmstack-off2] + number，之后跳到LABEL_331

  ![image-20240725110448988](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240725110448988.png)

- LABEL_331是所有case的最后一段代码，类似switch的所有case都没有break，然后都跳转到了default分支下

  ![image-20240725135938807](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240725135938807.png)

  LABEL_331有两个功能：

  - 改变控制流，做指令跳转

    - 一种是a1数组自增到下一个元素

      ```cpp
      a1 = (unsigned int *)(*(_QWORD *)beg + 4LL);
      *(_QWORD *)beg = a1;
      ```

    - 一种是直接跳转到a1数组的某个元素

      ```cpp
      //func_data - 0x18地址处保存的是上一个switch-case写入的值
      a1 = *(unsigned int **)(func_data - 0x18);
      *(_QWORD *)(func_data - 0x20) = 0LL;
      *(_QWORD *)beg = a1;
      ```

  - 调用回调函数

    ```cpp
    real_data = ((__int64 (__fastcall *)(_QWORD, _QWORD))func)(*v13, *v14);
    ```


- 最后，回到while(1)，继续走switch。

### 虚拟机结构剖析

- switch-case的参数来源：sub_F736C的第一个参数是一个4字节数组，每个4字节的一部分都是switch-case的参数，用来执行一个操作。

  ![image-20240725113411862](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240725113411862.png)

  因此每一个4字节就是一个handler，其handler的内部解析如下，handler index和subhandler index为switch-case的参数。

  ![image-20240725135546287](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240725135546287.png)

- handler的执行示例：

  ```
  handler index:0x2B
  subhandler index:0xC2B
  handler：[vm_stack-off3] = [vm_stack-off1] + [vm_stack-off2]
  example:
  [=] [Thread 2008]	index: 0xc2b -> [func_data-0x110] = [func_data-0x80] + [func_data-0x128]; 0xffffffffff971488, 0x555555cd9eb0, rs: 0x55555564b338
  ------------------------------------------------
  handler index:0x2B
  subhandler index:0xA6B
  handler:[vm_stack-off3] = [vm_stack-off1] >> operand2
  example:
  [=] [Thread 2008]	index: 0xa6b -> [func_data-0x128] = d[func_data-0x88] >> 0x18; 0x555f9370, rs: 0x55
  ------------------------------------------------
  handler index:0x9
  no subhandler index
  handler:[vm_stack-off1] = [vm_stack-off2] + operand1
  example:
  [=] [Thread 2008]	index: 0x9 -> [func_data-0x120] = [func_data-0x130] + 0x4; 0x0, rs: 0x4
  ```

  看第一个例子，index为0x2B，则进一步判断subindex，执行subindex为0xC2B的操作，这里有3个变量，off1、off2、off3，分别从handler中做位运算提取。

- 控制流的变化

  加解密的执行就是遍历handler数组实现的，一个handler一个handler的执行。对于for循环，虚拟机需要改变控制流来实现，以下给出控制流改变的一个例子：

  ```
  [=] [Thread 2008]	index: 0x34 -> [func_data-0x130]; 0x0
          [func_data-0x128]; 0x1
          [func_data-0x18] = index_table_pointer+4+((int)(0xfffc << 0x10) >> 0xE); 0x5555557e5bd0
          [func_data-0x20] = 2
  [=] [Thread 2008]	index: 0x9 -> [func_data-0x120] = [func_data-0x120] + 0x1; func_data-0x234, rs: func_data-0x233
          index_table_pointer = [func_data-0x18]; 0x5555557e5bc4
          [func_data-0x20] = 0
          [beg] = index_table_pointer
  ```

  执行0x34 handler，如果\*(DWORD\*)(func_data-0x130）!= \*(DWORD\*)(func_data-0x128），handler数组指针就减0xC，并且func_data-0x20地址处写入2，表示下一个handler执行后即将跳转：

  ```
  index_table_pointer+4+((int)(0xfffc << 0x10) >> 0xE) = index_table_pointer-0xC = 0x5555557e5bd0-0xC= 0x5555557e5bc4
  ```

  执行下一条0x9 handler时，因为func_data-0x20地址处的值为2，所以让handler跳转到0x5555557e5bc4。

  如果0x34 handler执行时\*(DWORD\*)(func_data-0x130）== \*(DWORD\*)(func_data-0x128），那么下一个handler执行后仍顺序执行。

### 虚拟机执行流程解析

每次执行一个handler，相当于进入switch走一遍，因为我们已经解析了handler4字节的内部组成，所以我们可以记录每一条handler具体代表的语义。每当进入switch时，我们把当前handler的语义打出来，就可以看到完整的加解密流程了。

![image-20240725141947203](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/libxx_algorithm_analysis/image-20240725141947203.png)

于是，我们调用ql.hook_code方法，每当执行到0xF7E20这，就打印handler语义：

更新custom_script.py:

```python
def custom_run_to_here(self, ql: Qiling) -> List[HookRet]:
	def addr_tps_F7E20_hook(ql: Qiling) -> None:
        # ql.log.info(f'index_base: {ql.arch.regs.X19:#x}')
        index = ql.arch.regs.X12 & 0x3F
        # ql.log.info(f'index_value: {index:#x}')
        # ql.log.info(f'off1: {ql.arch.regs.W8:#x}')
        # ql.log.info(f'off2: {ql.arch.regs.W9:#x}')

        indent = f'\n\t\t\t\t\t\t'
        off = calc_off(ql)
        W11 = calc_W11(ql)
        rs = f'index: {index:#x} -> '
        base_W8 = f'[func_data-{0x130-ql.arch.regs.W8*8:#x}]'
        base_W9 = f'[func_data-{0x130-ql.arch.regs.W9*8:#x}]'
        base_W10 = f'[func_data-{0x130-ql.arch.regs.W10*8:#x}]'

        global update_index_table_flag
        if update_index_table_flag == 2:
            update_index_table_flag += 1

        if index == 0x9 or index == 0x1C:
            base_W9_value = get_base_W9(ql)
            rs += f'{base_W8} = {base_W9} + {off:#x}; {get_base(ql, base_W9_value)}, rs: {get_base(ql, base_W9_value+off)}'
        elif index in [0, 0x34]:
            flag_20 = ql.arch.regs.X0
            if flag_20 != 0:
                rs += "ignore!!"
            v78 = f'(int)({off:#x} << 0x10) >> 0xE'
            v77 = get_base_W8(ql)
            rs += f'{base_W8}; {v77:#x}'
            v79 = get_base_W9(ql)
            rs += f'{indent}{base_W9}; {v79:#x}'

            str1 = f'{indent}[func_data-0x18] = index_table_pointer+8(2 elements); {ql.arch.regs.X19:#x}, rs: {ql.arch.regs.X19+8:#x}'
            str2 = f'{indent}[func_data-0x18] = index_table_pointer+4+({v78}); {ql.arch.regs.X19:#x}'
            if index == 0:
                if v77 != v79:
                    rs += str1
                else:
                    rs += str2

            if index == 0x34:
                if v77 == v79:
                    rs += str1
                else:
                    rs += str2
		# elif...

        if log_flag:
            ql.log.info(rs)

    return [ql.hook_address(addr_27DA8_hook, 0x7ffff7dfcda8),
            ql.hook_address(addr_27FB4_hook, 0x7ffff7dfcfb4),
            ql.hook_address(addr_tps_ADAB8_hook, 0x555555601ab8),
            ql.hook_address(addr_tps_F7E20_hook, 0x55555564be20)]
```

> - 完整的custom_script.py已上传至附件。
>
> - 因为switch-case有些路径是没有走到的，也就是说加解密的handler不是全集，所以我们在写handler的时候，只需要一个一个写，遇到一个新的待执行的handler，就增加一个elif，不需要把switch-case的所有路径都挨着写完。
>
> - 当我们新增handler时，就需要重启qiling环境，这样会很耗时。因此在遇到没有记录的handler时，我们可以手动调用ql.os.stop()，这样ql_run_to_here可以为我们保存当前执行环境，之后我们仍然可以单步模拟执行：
>
>   ```python
>   # qilingida.py
>   def ql_run_to_here(self):
>       # ...
>       userhook = None
>       if self.userobj is not None:
>           userhook = self.userobj.custom_run_to_here(self.qlemu.ql)
>       # 当qlemu.run方法在模拟执行时，如果custom_run_to_here调用了ql.os.stop(),
>       # 那么qlemu.run就会返回。
>       self.qlemu.run(end=curr_addr+self.qlemu.baseaddr-get_imagebase())
>       # qlemu.run返回后保存当前模拟执行环境。
>       self.qlemu.status = self.qlemu.ql.save()
>               
>   # custom_script.py
>   def custom_run_to_here(self, ql: Qiling) -> List[HookRet]:
>   	def next_pc(ql: Qiling, index = ""):
>           next_pc = ql.arch.regs.X1 - 0x555555554000
>           index = ql.arch.regs.X12 & 0x3F
>           rs = f'next unknown index: {index:#x} -> '
>           ql.log.info(rs + f'next pc: {next_pc:#x}')
>           ql.os.stop()
>           global log_flag
>           log_flag = False
>   ```

模拟执行的输出结果示例如下：

```
[=] [Thread 2008]	index: 0x9 -> [func_data-0x48] = [func_data-0x48] + 0xfea0; func_data-0x150, rs: func_data--0xfd50
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x158] = [func_data-0x38]; func_data-0x158, 0x0
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x150] = [func_data-0x80]; func_data-0x160, 0x0
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x148] = [func_data-0x88]; func_data-0x168, 0x0
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x140] = [func_data-0x90]; func_data-0x170, 0x0
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x138] = [func_data-0x98]; func_data-0x178, 0x0
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x130] = [func_data-0xa0]; func_data-0x180, 0x0
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x128] = [func_data-0xa8]; func_data-0x188, 0x0
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x120] = [func_data-0xb0]; func_data-0x190, 0x0
[=] [Thread 2008]	index: 0x3c -> [func_data-0xb0] = [[func_data-0x110] + 0x10]; func_data-0x450 -> func_data-0x440, 0x20
[=] [Thread 2008]	index: 0x3c -> [func_data-0xa8] = [[func_data-0x110] + 0x8]; func_data-0x450 -> func_data-0x448, 0x100000
[=] [Thread 2008]	index: 0x3c -> [func_data-0x90] = [[func_data-0x108] + 0x0]; 0x555555857110 -> 0x555555857110, 0x555555f0abb0
[=] [Thread 2008]	index: 0x35 -> [func_data-0x88] = (signed )d[[func_data-0x110] + 0x0]; func_data-0x450, 0x555f9370
[=] [Thread 2008]	index: 0x3c -> [func_data-0x128] = [[func_data-0x100] + 0x0]; 0x555555857118 -> 0x555555857118, 0x555555cd9eb0
[=] [Thread 2008]	index: 0x2d -> [func_data-0x98] = d[func_data-0x130] + (int64)(int)0x0; 0x0, rs: 0x0
[=] [Thread 2008]	index: 0x2a -> b[[func_data-0x48] + 0x110] = b[func_data-0x130]; func_data-0x1a0, 0x0
[=] [Thread 2008]	index: 0x9 -> [func_data-0xa0] = [func_data-0x48] + 0x4; func_data-0x2b0, rs: func_data-0x2ac
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x108] = [func_data-0xa0]; func_data-0x1a8, func_data-0x2ac
[=] [Thread 2008]	index: 0x9 -> [func_data-0x120] = [func_data-0x130] + 0x4; 0x0, rs: 0x4
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x118] = [func_data-0x120]; func_data-0x198, 0x4
[=] [Thread 2008]	index: 0x1f -> [func_data-0x120] = int(0xff97 << 0x10)
[=] [Thread 2008]	index: 0x1d -> [func_data-0x80] = [func_data-0x120] | 0x1488; 0xffffffffff970000, rs:0xffffffffff971488
[=] [Thread 2008]	index: 0xc2b -> [func_data-0x110] = [func_data-0x80] + [func_data-0x128]; 0xffffffffff971488, 0x555555cd9eb0, rs: 0x55555564b338
[=] [Thread 2008]	index: 0x92b -> [func_data-0x68] = [func_data-0x130] | [func_data-0xf8]; 0x0, 0x55555564b34c, rs: 0x55555564b34c
[=] [Thread 2008]	index: 0xdeb -> [func_data-0x18] = [func_data-0x68]; 0x55555564b34c
						[func_data-0x20] = 2
						[func_data-0x38] = index_table_pointer+8; 0x5555557e5b90, rs: 0x5555557e5b98
						[func_data-0x10] = index_table_pointer+8; 0x5555557e5b90, rs: 0x5555557e5b98
[=] [Thread 2008]	index: 0x9 -> [func_data-0x108] = [func_data-0x48] + 0x108; func_data-0x2b0, rs: func_data-0x1a8
						index_table_pointer = [func_data-0x18]; 0x55555564b34c
						[func_data-0x20] = 0
						[beg] = index_table_pointer
						call func:(0x55555564b34c)([func_data-0x110], [func_data-0x108]); memset
						index_table_pointer = [func_data-0x10]; 0x5555557e5b98
						[beg] = index_table_pointer
[=] [Thread 2008]	index: 0xa6b -> [func_data-0x128] = d[func_data-0x88] >> 0x18; 0x555f9370, rs: 0x55
[=] [Thread 2008]	index: 0xa6b -> [func_data-0x120] = d[func_data-0x88] >> 0x10; 0x555f9370, rs: 0x555f
[=] [Thread 2008]	index: 0xa6b -> [func_data-0x118] = d[func_data-0x88] >> 0x8; 0x555f9370, rs: 0x555f93
[=] [Thread 2008]	index: 0x2a -> b[[func_data-0x48] + 0x5] = b[func_data-0x118]; func_data-0x2ab, 0x93
[=] [Thread 2008]	index: 0x2a -> b[[func_data-0x48] + 0x4] = b[func_data-0x88]; func_data-0x2ac, 0x70
[=] [Thread 2008]	index: 0x2a -> b[[func_data-0x48] + 0x6] = b[func_data-0x120]; func_data-0x2aa, 0x5f
[=] [Thread 2008]	index: 0x2a -> b[[func_data-0x48] + 0x7] = b[func_data-0x128]; func_data-0x2a9, 0x55
[=] [Thread 2008]	index: 0xc2b -> [func_data-0x118] = [func_data-0x80] + [func_data-0x90]; 0xffffffffff971488, 0x555555f0abb0, rs: 0x55555587c038
[=] [Thread 2008]	index: 0x38 -> [func_data-0x128] = [func_data-0x98] < 0x100; 0x0, rs: 0x1
```

## 加解密算法分析

观察sub_F736C返回前，所有handler的执行记录，主要分为四部分：

> handler执行过程.txt已上传至附件，里面记录了整个执行流程。

### 环境初始化

虚拟栈的初始化已经sub_F736C的参数保存到虚拟栈：

```
[=] [Thread 2008]	index: 0x9 -> [func_data-0x48] = [func_data-0x48] + 0xfea0; func_data-0x150, rs: func_data--0xfd50
//这里分号后面为自动生成的注释，表示从左到右，其内存的值。比如下面这一行，[func_data-0x48]的值是func_data-0x158；[func_data-0x38]的值是0。因为这是个写操作，就没有打印[[func_data-0x48]+0x158]的值了。
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x158] = [func_data-0x38]; func_data-0x158, 0x0
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x150] = [func_data-0x80]; func_data-0x160, 0x0
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x148] = [func_data-0x88]; func_data-0x168, 0x0
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x140] = [func_data-0x90]; func_data-0x170, 0x0
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x138] = [func_data-0x98]; func_data-0x178, 0x0
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x130] = [func_data-0xa0]; func_data-0x180, 0x0
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x128] = [func_data-0xa8]; func_data-0x188, 0x0
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x120] = [func_data-0xb0]; func_data-0x190, 0x0
[=] [Thread 2008]	index: 0x3c -> [func_data-0xb0] = [[func_data-0x110] + 0x10]; func_data-0x450 -> func_data-0x440, 0x20
[=] [Thread 2008]	index: 0x3c -> [func_data-0xa8] = [[func_data-0x110] + 0x8]; func_data-0x450 -> func_data-0x448, 0x100000
[=] [Thread 2008]	index: 0x3c -> [func_data-0x90] = [[func_data-0x108] + 0x0]; 0x555555857110 -> 0x555555857110, 0x555555f0abb0
[=] [Thread 2008]	index: 0x35 -> [func_data-0x88] = (signed )d[[func_data-0x110] + 0x0]; func_data-0x450, 0x555f9370
[=] [Thread 2008]	index: 0x3c -> [func_data-0x128] = [[func_data-0x100] + 0x0]; 0x555555857118 -> 0x555555857118, 0x555555cd9eb0
[=] [Thread 2008]	index: 0x2d -> [func_data-0x98] = d[func_data-0x130] + (int64)(int)0x0; 0x0, rs: 0x0
[=] [Thread 2008]	index: 0x2a -> b[[func_data-0x48] + 0x110] = b[func_data-0x130]; func_data-0x1a0, 0x0
[=] [Thread 2008]	index: 0x9 -> [func_data-0xa0] = [func_data-0x48] + 0x4; func_data-0x2b0, rs: func_data-0x2ac
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x108] = [func_data-0xa0]; func_data-0x1a8, func_data-0x2ac
[=] [Thread 2008]	index: 0x9 -> [func_data-0x120] = [func_data-0x130] + 0x4; 0x0, rs: 0x4
[=] [Thread 2008]	index: 0x29 -> [[func_data-0x48]+0x118] = [func_data-0x120]; func_data-0x198, 0x4
[=] [Thread 2008]	index: 0x1f -> [func_data-0x120] = int(0xff97 << 0x10)
[=] [Thread 2008]	index: 0x1d -> [func_data-0x80] = [func_data-0x120] | 0x1488; 0xffffffffff970000, rs:0xffffffffff971488
[=] [Thread 2008]	index: 0xc2b -> [func_data-0x110] = [func_data-0x80] + [func_data-0x128]; 0xffffffffff971488, 0x555555cd9eb0, rs: 0x55555564b338
[=] [Thread 2008]	index: 0x92b -> [func_data-0x68] = [func_data-0x130] | [func_data-0xf8]; 0x0, 0x55555564b34c, rs: 0x55555564b34c
[=] [Thread 2008]	index: 0xdeb -> [func_data-0x18] = [func_data-0x68]; 0x55555564b34c
						[func_data-0x20] = 2
						[func_data-0x38] = index_table_pointer+8; 0x5555557e5b90, rs: 0x5555557e5b98
						[func_data-0x10] = index_table_pointer+8; 0x5555557e5b90, rs: 0x5555557e5b98
[=] [Thread 2008]	index: 0x9 -> [func_data-0x108] = [func_data-0x48] + 0x108; func_data-0x2b0, rs: func_data-0x1a8
						index_table_pointer = [func_data-0x18]; 0x55555564b34c
						[func_data-0x20] = 0
						[beg] = index_table_pointer
						call func:(0x55555564b34c)([func_data-0x110], [func_data-0x108]); memset
						index_table_pointer = [func_data-0x10]; 0x5555557e5b98
						[beg] = index_table_pointer
```

### 准备一个256字节大小的S-box表

读取[func_data-0x98]的一个字节，赋值给func_data-0x2a8地址处，同时[func_data-0x98]和[func_data-0x120]都自增1，直到[func_data-0x98]==0x100。

```
[=] [Thread 2008]	index: 0x2a -> b[[func_data-0x120] + 0x0] = b[func_data-0x98]; func_data-0x2a8, 0x0
[=] [Thread 2008]	index: 0x2d -> [func_data-0x98] = d[func_data-0x98] + (int64)(int)0x1; 0x0, rs: 0x1
[=] [Thread 2008]	index: 0x38 -> [func_data-0x128] = [func_data-0x98] < 0x100; 0x1, rs: 0x1
[=] [Thread 2008]	index: 0x34 -> [func_data-0x130]; 0x0
						[func_data-0x128]; 0x1
						[func_data-0x18] = index_table_pointer+4+((int)(0xfffc << 0x10) >> 0xE); 0x5555557e5bd0
						[func_data-0x20] = 2
[=] [Thread 2008]	index: 0x9 -> [func_data-0x120] = [func_data-0x120] + 0x1; func_data-0x2a8, rs: func_data-0x2a7
						index_table_pointer = [func_data-0x18]; 0x5555557e5bc4
						[func_data-0x20] = 0
						[beg] = index_table_pointer
[=] [Thread 2008]	index: 0x2a -> b[[func_data-0x120] + 0x0] = b[func_data-0x98]; func_data-0x2a7, 0x1
[=] [Thread 2008]	index: 0x2d -> [func_data-0x98] = d[func_data-0x98] + (int64)(int)0x1; 0x1, rs: 0x2
[=] [Thread 2008]	index: 0x38 -> [func_data-0x128] = [func_data-0x98] < 0x100; 0x2, rs: 0x1
[=] [Thread 2008]	index: 0x34 -> [func_data-0x130]; 0x0
						[func_data-0x128]; 0x1
						[func_data-0x18] = index_table_pointer+4+((int)(0xfffc << 0x10) >> 0xE); 0x5555557e5bd0
						[func_data-0x20] = 2
[=] [Thread 2008]	index: 0x9 -> [func_data-0x120] = [func_data-0x120] + 0x1; func_data-0x2a7, rs: func_data-0x2a6
						index_table_pointer = [func_data-0x18]; 0x5555557e5bc4
						[func_data-0x20] = 0
						[beg] = index_table_pointer
[=] [Thread 2008]	index: 0x2a -> b[[func_data-0x120] + 0x0] = b[func_data-0x98]; func_data-0x2a6, 0x2
[=] [Thread 2008]	index: 0x2d -> [func_data-0x98] = d[func_data-0x98] + (int64)(int)0x1; 0x2, rs: 0x3
[=] [Thread 2008]	index: 0x38 -> [func_data-0x128] = [func_data-0x98] < 0x100; 0x3, rs: 0x1
[=] [Thread 2008]	index: 0x34 -> [func_data-0x130]; 0x0
						[func_data-0x128]; 0x1
						[func_data-0x18] = index_table_pointer+4+((int)(0xfffc << 0x10) >> 0xE); 0x5555557e5bd0
						[func_data-0x20] = 2
[=] [Thread 2008]	index: 0x9 -> [func_data-0x120] = [func_data-0x120] + 0x1; func_data-0x2a6, rs: func_data-0x2a5
						index_table_pointer = [func_data-0x18]; 0x5555557e5bc4
						[func_data-0x20] = 0
						[beg] = index_table_pointer
```

以上逻辑用C++实现如下：

```cpp
#define SHUFFLE_TABLE_LEN 256

unsigned char shuffle_table[SHUFFLE_TABLE_LEN] = { 0 };
for (int i = 0; i < SHUFFLE_TABLE_LEN; ++i)
    shuffle_table[i] = i;
```

### S-box表置换

遍历S-box表，i从0自增到255：

```
//读取S-box表的第i个元素 a
[=] [Thread 2008]	index: 0x72b -> [func_data-0x128] = (int)d[func_data-0x120] >> 0x1f; 0x0
[=] [Thread 2008]	index: 0xa6b -> [func_data-0xe0] = d[func_data-0x128] >> 0x1b; 0x0, rs: 0x0
[=] [Thread 2008]	index: 0xcab -> [func_data-0xe0] = d[func_data-0xe0] + d[func_data-0x120]; 0x0, 0x0, rs: 0x0
[=] [Thread 2008]	index: 0x9eb -> [func_data-0xe0] = [func_data-0x108] & [func_data-0xe0]; 0xffffffffffffffe0, 0x0, rs: 0x0
[=] [Thread 2008]	index: 0xb2b -> [func_data-0xe0] = d[func_data-0x120] - d[func_data-0xe0]; 0x0, 0x0, rs: 0x0
[=] [Thread 2008]	index: 0x4ab -> [func_data-0xe0] = d[func_data-0xe0] << 0x0; 0x0
[=] [Thread 2008]	index: 0x9 -> [func_data-0xd8] = [func_data-0xf0] + 0x1; func_data-0x2a8, rs: func_data-0x2a7
[=] [Thread 2008]	index: 0x30 -> [func_data-0xd0] = b[[func_data-0xf0] + 0x0]; func_data-0x2a8, 0x0

// S-box表的第i个元素和上一轮结果相加：a+last_result
// last_result初始化为0
[=] [Thread 2008]	index: 0xcab -> [func_data-0xe8] = d[func_data-0xd0] + d[func_data-0xe8]; 0x0, 0x0, rs: 0x0

// [func_data-0x118]是sub_F736C函数的第3个参数，是一个0x20字节的数组，元素长度为1，这里命名为shuffle_factor_table。
// 从shuffle_factor_table取(i%0x20)，然后与上一步相加：
// 得 a+last_result+shuffle_factor_table[i%0x20]
[=] [Thread 2008]	index: 0x2d -> [func_data-0xc8] = d[func_data-0x120] + (int64)(int)0x1; 0x0, rs: 0x1
[=] [Thread 2008]	index: 0xa6b -> [func_data-0x128] = d[func_data-0x128] >> 0x1e; 0x0, rs: 0x0
[=] [Thread 2008]	index: 0xc2b -> [func_data-0xe0] = [func_data-0xe0] + [func_data-0x118]; 0x0, 0x55555587c038, rs: 0x55555587c038
[=] [Thread 2008]	index: 0x30 -> [func_data-0xe0] = b[[func_data-0xe0] + 0x0]; 0x55555587c038, 0x48
[=] [Thread 2008]	index: 0xcab -> [func_data-0xe8] = d[func_data-0xe0] + d[func_data-0xe8]; 0x48, 0x0, rs: 0x48

// tps_encrypt和tps_decrypt的第一个参数serino，小端序保存在内存中，然后取出一字节与上一步相加：
// 地 a+last_result+shuffle_factor_table[i%0x20]+serino[i%4]
[=] [Thread 2008]	index: 0xcab -> [func_data-0x128] = d[func_data-0x128] + d[func_data-0x120]; 0x0, 0x0, rs: 0x0
[=] [Thread 2008]	index: 0x9eb -> [func_data-0x128] = [func_data-0xf8] & [func_data-0x128]; 0xfffffffffffffffc, 0x0, rs: 0x0
[=] [Thread 2008]	index: 0xb2b -> [func_data-0x128] = d[func_data-0x120] - d[func_data-0x128]; 0x0, 0x0, rs: 0x0
[=] [Thread 2008]	index: 0x4ab -> [func_data-0x128] = d[func_data-0x128] << 0x0; 0x0
[=] [Thread 2008]	index: 0xc2b -> [func_data-0x128] = [func_data-0x128] + [func_data-0xa0]; 0x0, func_data-0x2ac, rs: func_data-0x2ac
[=] [Thread 2008]	index: 0x30 -> [func_data-0x128] = b[[func_data-0x128] + 0x0]; func_data-0x2ac, 0x70
[=] [Thread 2008]	index: 0xcab -> [func_data-0x128] = d[func_data-0x128] + d[func_data-0xe8]; 0x70, 0x48, rs: 0xb8

// 上一步结果与0xFF求余
// 得 last_result = (a+last_result+shuffle_factor_table[i%0x20]+serino[i%4]) & 0xFF
[=] [Thread 2008]	index: 0x72b -> [func_data-0x120] = (int)d[func_data-0x128] >> 0x1f; 0xb8
[=] [Thread 2008]	index: 0xa6b -> [func_data-0x120] = d[func_data-0x120] >> 0x18; 0x0, rs: 0x0
[=] [Thread 2008]	index: 0xcab -> [func_data-0x120] = d[func_data-0x120] + d[func_data-0x128]; 0x0, 0xb8, rs: 0xb8
[=] [Thread 2008]	index: 0x9eb -> [func_data-0x120] = [func_data-0x100] & [func_data-0x120]; 0xffffffffffffff00, 0xb8, rs: 0x0
[=] [Thread 2008]	index: 0xb2b -> [func_data-0xe8] = d[func_data-0x128] - d[func_data-0x120]; 0xb8, 0x0, rs: 0xb8
[=] [Thread 2008]	index: 0x4ab -> [func_data-0x128] = d[func_data-0xe8] << 0x0; 0xb8

// S-box表置换
// tmp = S-box[i]
// S-box[i] = S-box[last_result]
// S-box[last_result] = tmp
[=] [Thread 2008]	index: 0xc2b -> [func_data-0x128] = [func_data-0x128] + [func_data-0x110]; 0xb8, func_data-0x2a8, rs: func_data-0x1f0
[=] [Thread 2008]	index: 0x30 -> [func_data-0x120] = b[[func_data-0x128] + 0x0]; func_data-0x1f0, 0xb8
[=] [Thread 2008]	index: 0x2a -> b[[func_data-0xf0] + 0x0] = b[func_data-0x120]; func_data-0x2a8, 0xb8
[=] [Thread 2008]	index: 0x2a -> b[[func_data-0x128] + 0x0] = b[func_data-0xd0]; func_data-0x1f0, 0x0
[=] [Thread 2008]	index: 0x92b -> [func_data-0x120] = [func_data-0x130] | [func_data-0xc8]; 0x0, 0x1, rs: 0x1

// 没有遍历到0x256，回调到S-box置换的第一条指令，继续置换
[=] [Thread 2008]	index: 0x38 -> [func_data-0x128] = [func_data-0x120] < 0x100; 0x1, rs: 0x1
[=] [Thread 2008]	index: 0x34 -> [func_data-0x130]; 0x0
						[func_data-0x128]; 0x1
						[func_data-0x18] = index_table_pointer+4+((int)(0xffde << 0x10) >> 0xE); 0x5555557e5c80
						[func_data-0x20] = 2
[=] [Thread 2008]	index: 0x92b -> [func_data-0xf0] = [func_data-0x130] | [func_data-0xd8]; 0x0, 0x80000000db39, rs: func_data-0x2a7
						index_table_pointer = [func_data-0x18]; 0x5555557e5bfc
						[func_data-0x20] = 0
						[beg] = index_table_pointer
```

以上逻辑用C++实现如下：

```cpp
void Fisher_Yates(unsigned char shuffle_table[SHUFFLE_TABLE_LEN], unsigned int serino) {

    unsigned char shuffle_factor_table[SHUFFLE_FACTOR_TABLE_LEN] = { 
        0x48, 0xA9, 0xC8, 0x12, 0xCA, 0xFC, 0xD3, 0x5E, 0xB7, 0x61, 0x50, 0x17, 0x68, 0xBA, 0x7E, 0x2E, 
        0xB9, 0xA2, 0x38, 0x85, 0x35, 0x48, 0x55, 0x6C, 0x2C, 0x38, 0x43, 0x1F, 0x51, 0xD6, 0x30, 0x30 };

    unsigned char last_result = 0;
    unsigned char serino_table[] = { serino & 0xFF, (serino >> 8) & 0xFF, (serino >> 16) & 0xFF, (serino >> 24) & 0xFF };

    for (int i = 0; i < SHUFFLE_TABLE_LEN; ++i) {
        last_result = (shuffle_factor_table[i % SHUFFLE_FACTOR_TABLE_LEN] + shuffle_table[i] + last_result + serino_table[i % 4]) & 0xFF;
        unsigned char tmp = shuffle_table[i];
        shuffle_table[i] = shuffle_table[last_result];
        shuffle_table[last_result] = tmp;
        //printf("exchange: %x -> %x, factor: %x\n", i, last_result, shuffle_factor_table[i%SHUFFLE_FACTOR_TABLE_LEN]);
    }
}
```

### 数据加解密

遍历待加解密的数据，i从0到len(data)-1

```
// a = (i+1) & 0xFF
[=] [Thread 2008]	index: 0x2d -> [func_data-0x128] = d[func_data-0x120] + (int64)(int)0x1; 0x100, rs: 0x101
[=] [Thread 2008]	index: 0x72b -> [func_data-0x120] = (int)d[func_data-0x128] >> 0x1f; 0x101
[=] [Thread 2008]	index: 0xa6b -> [func_data-0x120] = d[func_data-0x120] >> 0x18; 0x0, rs: 0x0
[=] [Thread 2008]	index: 0xcab -> [func_data-0x120] = d[func_data-0x120] + d[func_data-0x128]; 0x0, 0x101, rs: 0x101
[=] [Thread 2008]	index: 0x9eb -> [func_data-0x120] = [func_data-0x118] & [func_data-0x120]; 0xffffffffffffff00, 0x101, rs: 0x100
[=] [Thread 2008]	index: 0xb2b -> [func_data-0x120] = d[func_data-0x128] - d[func_data-0x120]; 0x101, 0x100, rs: 0x1
[=] [Thread 2008]	index: 0x4ab -> [func_data-0x128] = d[func_data-0x120] << 0x0; 0x1

// func_data-0xa8为待加解密的数据，这里命名为x
// 保存当前的字节x[i]到[func_data-0x100]
[=] [Thread 2008]	index: 0x9 -> [func_data-0xf8] = [func_data-0x100] + 0x1; 0x0, rs: 0x1
[=] [Thread 2008]	index: 0xc2b -> [func_data-0x100] = [func_data-0x100] + [func_data-0xa8]; 0x0, 0x100000, rs: 0x100000

// func_data-0x110保存着S-box的地址
// 从置换后的S-box取出一字节，index为a，并与上一轮结果相加
// 得b = S-box[a]+last_result
[=] [Thread 2008]	index: 0xc2b -> [func_data-0x128] = [func_data-0x128] + [func_data-0x110]; 0x1, func_data-0x2a8, rs: func_data-0x2a7
[=] [Thread 2008]	index: 0x30 -> [func_data-0xf0] = b[[func_data-0x128] + 0x0]; func_data-0x2a7, 0xa9
[=] [Thread 2008]	index: 0xcab -> [func_data-0x108] = d[func_data-0xf0] + d[func_data-0x108]; 0xa9, 0x0, rs: 0xa9
[=] [Thread 2008]	index: 0x72b -> [func_data-0xe8] = (int)d[func_data-0x108] >> 0x1f; 0xa9
[=] [Thread 2008]	index: 0xa6b -> [func_data-0xe8] = d[func_data-0xe8] >> 0x18; 0x0, rs: 0x0
[=] [Thread 2008]	index: 0xcab -> [func_data-0xe8] = d[func_data-0xe8] + d[func_data-0x108]; 0x0, 0xa9, rs: 0xa9
[=] [Thread 2008]	index: 0x9eb -> [func_data-0xe8] = [func_data-0x118] & [func_data-0xe8]; 0xffffffffffffff00, 0xa9, rs: 0x0
[=] [Thread 2008]	index: 0xb2b -> [func_data-0x108] = d[func_data-0x108] - d[func_data-0xe8]; 0xa9, 0x0, rs: 0xa9
[=] [Thread 2008]	index: 0x4ab -> [func_data-0xe8] = d[func_data-0x108] << 0x0; 0xa9

// S-box表置换
// tmp = S-box[a]
// S-box[a] = S-box[b]
// S-box[b] = S-box[a]
[=] [Thread 2008]	index: 0xc2b -> [func_data-0xe8] = [func_data-0xe8] + [func_data-0x110]; 0xa9, func_data-0x2a8, rs: func_data-0x1ff
[=] [Thread 2008]	index: 0x30 -> [func_data-0xe0] = b[[func_data-0xe8] + 0x0]; func_data-0x1ff, 0xc1
[=] [Thread 2008]	index: 0x2a -> b[[func_data-0x128] + 0x0] = b[func_data-0xe0]; func_data-0x2a7, 0xc1
[=] [Thread 2008]	index: 0x2a -> b[[func_data-0xe8] + 0x0] = b[func_data-0xf0]; func_data-0x1ff, 0xa9

// x[i] = x[i] ^ ((S-box[a] + tmp) & 0xFF)
[=] [Thread 2008]	index: 0x30 -> [func_data-0x128] = b[[func_data-0x128] + 0x0]; func_data-0x2a7, 0xc1
[=] [Thread 2008]	index: 0xcab -> [func_data-0x128] = d[func_data-0xf0] + d[func_data-0x128]; 0xa9, 0xc1, rs: 0x16a
[=] [Thread 2008]	index: 0x30 -> [func_data-0xf0] = b[[func_data-0x100] + 0x0]; 0x100000, 0x12
[=] [Thread 2008]	index: 0x37 -> [func_data-0x128] = [func_data-0x128] & 0xff; 0x16a, rs:0x6a
[=] [Thread 2008]	index: 0x7 -> [func_data-0x128] = ((1(LL) << (W10+1)) - 1) & ([func_data-0x128] >> W11); 0x1f, 0x6a, 0x0, rs: 0x6a
[=] [Thread 2008]	index: 0xc2b -> [func_data-0x128] = [func_data-0x128] + [func_data-0x110]; 0x6a, func_data-0x2a8, rs: func_data-0x23e
[=] [Thread 2008]	index: 0x30 -> [func_data-0x128] = b[[func_data-0x128] + 0x0]; func_data-0x23e, 0xef
[=] [Thread 2008]	index: 0x36b -> [func_data-0x128] = [func_data-0x128] ^ [func_data-0xf0]; 0xef, 0x12, rs: 0xfd
[=] [Thread 2008]	index: 0x2a -> b[[func_data-0x100] + 0x0] = b[func_data-0x128]; 0x100000, 0xfd

// 没有遍历到x的长度，继续遍历
[=] [Thread 2008]	index: 0x92b -> [func_data-0x100] = [func_data-0x130] | [func_data-0xf8]; 0x0, 0x1, rs: 0x1
[=] [Thread 2008]	index: 0x1eb -> base_W9_value < base_W8_value: [func_data-0x128] = 1; w8=[func_data-0xb0]=32, w9=[func_data-0x100]=1
[=] [Thread 2008]	index: 0x34 -> [func_data-0x130]; 0x0
						[func_data-0x128]; 0x1
						[func_data-0x18] = index_table_pointer+4+((int)(0xffde << 0x10) >> 0xE); 0x5555557e5d24
						[func_data-0x20] = 2
[=] [Thread 2008]	index: 0x4ab -> [func_data-0x130] = d[func_data-0x130] << 0x0; 0x0
						index_table_pointer = [func_data-0x18]; 0x5555557e5ca0
						[func_data-0x20] = 0
						[beg] = index_table_pointer
```

以上逻辑用C++实现如下：

```cpp
void encrypt_and_decrypt_data(unsigned char shuffle_table[SHUFFLE_TABLE_LEN], unsigned char* x, int len) {

    unsigned char last_result = 0;

    for (int i = 0; i < len; ++i) {

        int s_i = (i + 1) & 0xFF;
        unsigned char cur = shuffle_table[s_i];

        // last_result = (last_result + cur) & 0xFF;
        last_result += cur; // no need to 'and 0xFF', because the type of last_result is unsigned char

        shuffle_table[s_i] = shuffle_table[last_result];
        shuffle_table[last_result] = cur;

        unsigned char tmp = (cur + shuffle_table[s_i]) & 0xFF;
        x[i] = x[i] ^ shuffle_table[tmp];
    }
}
```

## 总结

第一次使用qiling来做模拟执行，踩了不少坑。不过这些坑填完了，之后模拟执行就会方便很多。

libxx.so的加解密算法很简单，相信大家已经能看出来这个是RC4，不过稍微有一点魔改，把密钥分成了两部分。

加解密算法的保护主要还是通过虚拟机来实现的，其中也有一点花指令和动态字符串解密，不过这些在libxx.so里都很简单，所以没有细说。

希望本文可以给想用qiling做模拟执行的朋友一些提示，快速过掉qiling的一些坑。
