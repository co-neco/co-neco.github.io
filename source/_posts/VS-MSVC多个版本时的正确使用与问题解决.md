---
title: VisualStudio MSVC有多个版本时，如何正确使用低版本来编译工程和使用VS Command Prompt
categories:
  - Technology
  - Development
date: 2021-08-04 23:17:01
tags:
 - VS
 - Visual Studio
 - MSVC
 - toolset
 - 工具集
---

### 本文产生的原因

最近在用VS 2019来编译兼容WinXP的程序时，发现高版本(14.29.xxxxx)的MSVC的runtime代码部分不兼容winXP。之后使用低版本（14.25.xxxxx）的MSVC就可以运行在winXP上，所以本文的目的是记录整个问题的解决工程，方便其他朋友参考。

> 以上方案解决的问题如下：
>
> 用“Visual Studio 2017 - Windows XP (v141_xp)”工具集，使用14.29.xxxx版本的MSVC编译程序，最后程序在winXP无法运行，报错“无法定位程序输入点InitializeCriticalSectionEx于动态链接库 KERNEL32.dll上”。
>
> 这个错误的原因是14.29.xxxx版本的MSVC不兼容winXP，直接使用了InitializeCriticalSectionEx函数，该函数从winVista开始支持。

### MSVC多版本的需求

如果工程需要支持Win7、WinXP等低版本，且有用VS 2019的需求，那么此时就需要安装MSVC的低版本工具集。

> 使用多版本的情况，一般存在于使用VS 2019版本时。因为高版本的MSVC不兼容winXP，所以我们需要用低版本的MSVC去编译工程。（VS 2019安装时会默认安装最高版本，如果手动去除，会导致很多配置问题，所以不能去除）
> 如果大家有需求要兼容低版本的windows，请下载VS 2017。VS 2017附带的MSVC版本为14.16.xxxxx，用该版本已足够编译兼容低版本的windows的程序，且不会遇到本文提到的问题。

### MSVC多版本的安装

打开Visual Studio Installer，转到“修改”界面，在“单个组件”中搜索“MSVC”，可安装多个版本。

> 注：
>
> - 如果要支持WinXP，还需要下载“**C++ Windows XP Support for VS 2017 (v141) tools [Deprecated]**”。
> - 关于WinXP的兼容编译，请参考[Configuring Programs for Windows XP](https://docs.microsoft.com/en-us/cpp/build/configuring-programs-for-windows-xp)

### MSVC多版本的编译

#### 选择MSVC版本

索引到工程属性*Configuration Properies*，“General->Platform Toolset”选择v142版本的工具集，“Advanced->MSVC Toolset Version”选择你需要的MSVC版本。

> 如果你要用v141工具集，可在以上操作之后，再将“General->Platform Toolset”切换到v141。因为切换到v141之后，*Configuration Properies*下就没有Advanced选项了。

#### 编译需要用VS Command Prompt来编译的库

这里拿boost举例。

为选择低版本的MSVC编译，需要给vcvarsall.bat设置参数，改变MSVC版本。

> 这里改变MSVC版本，将会设置一些对应的环境变量，比如INCLUDE、LIBPATH路径等。

方法（举例：x86 Native Tools Command Prompt for VS 2019）：

- 点击“开始”，搜索command，右键出现的“x86 Native Tools Command Prompt for VS 2019”，找到文件位置

- 右键该文件，找到“目标”一栏，该栏描述了该快捷文件执行的命令，默认命令是：%comspec% /k "C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvars32.bat"

- 在该命令的最后添加：x86(architecture/架构) -vcvars_ver=14.25(不是14.25.xxxxx)，添加后如下：

  ```bash
  %comspec% /k "C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvars32.bat" x86 -vcvars_ver=14.25
  ```

> 注：windows SDk根据情况，你可能会有多个。因为历史原因，有些SDK是残缺的，当VS command prompt根据名称顺序找到这些SDK的时候，编译时会报各种文件找不到的错误。这时，我们需要把这些残缺的SDK删掉。
>
> > eg：
> >
> > C:\Windows Kits\10\Include目录下有三个文件夹，10.0.17763.0、10.0.10240.0、10.0.20348.0。
> >
> > 其中10.0.20348.0是残缺的SDK，但因为降序的原因，10.0.20348.0会作为编译是的Windows SDK，而其他两个则不会被用到。

### 参考

- [Use the Microsoft C++ toolset from the command line ...](https://docs.microsoft.com/en-us/cpp/build/building-on-the-command-line)

- [Configuring Programs for Windows XP](https://docs.microsoft.com/en-us/cpp/build/configuring-programs-for-windows-xp)
