---
title: C++工程预编译笔记.md
categories:
  - Technology
  - Development
date: 2023-06-29 21:04:06
tags:
  - compilation
  - c++
  - windows
  - vs
---

随着一个工程的逐渐壮大，工程的编译时间会越来越长，也许你觉得编译时间长是正常的，因为引入了各种库，又开发了很多代码。

开发一个工程很长时间了，编译要花大概100秒左右，每次需要rebuild或者出包时都会觉得很慢，但也只能等待。无意间了解到一个预编译的概念，于是决定对整个工程添加预编译，看编译时间能否有明显变化。结果让我很吃惊，编译时间从100秒降到了17秒，让我之后的开发也相对快速了一点。这里记录一下过程和其中值得记录的点。

## 预编译（precompiled header）

预编译就是把需要包含的头文件预先编译成一种中间形式，这样在之后的编译中，每遇到这些已经编译过的头文件，就可以利用之前生成的中间形式，从而减少编译时长。

> - 预编译的资料可以查看[wiki](https://en.wikipedia.org/wiki/Precompiled_header)和[msdn](https://learn.microsoft.com/en-us/cpp/build/creating-precompiled-header-files?view=msvc-170)。
>
> - #pragma once和预编译是有区别的，#pragma once只是一个include guards(包含保护)，防止多次包含，但编译时还是要编译到每个编译单元的（conpilation unit）。

## VS使用预编译

VS使用预编译的步骤很简单，可查看[善用预编译PCH文件提升编译速度](https://baijiahao.baidu.com/s?id=1666271161172135646&wfr=spider&for=pc)。

> - 使用预编译后，每个源文件(.c或.cpp)都需要包含pch.h（这个头文件名可随意设置），这个比较繁琐，可以使用VS的/FI选项，该选项可以默认给所有源文件添加pch.h。
> - 不过在stackoverflow中，有很多人不同意使用/FI选项，原因如下
>   - 使用/FI后，新的阅读者更难理解文件之间的依赖关系
>   - 使用/FI后，不好跨平台兼容，比如在linux上的gcc编译（不过gcc也有对应的设置）

## VS预编译初体验

因为工程中有一个common目录，这个目录的头文件包含了一些通用的宏和类定义，所以很多地方都使用了，于是我的第一个目标就是把这个目录的头文件放到pch.h文件，然后设置VS关于预编译的配置，最后编译，结果是减少了大概2到3秒。

对于这个结果，我不是很满意，预编译的效果不是很明显。

## 微软的开源工具vcperf

该工具配合WPA(Windows Performance Analyzer)，可以查看编译的整个过程细节，方便我们：

- 确认是否有并行编译
- 确认哪些文件需要放到预编译文件里(pch.h)
- 确认编译时间中哪些文件耗时较长，方便分析定位不合理的头文件包含

> 相关介绍可查看[Get started with C++ Build Insights](https://learn.microsoft.com/en-us/cpp/build-insights/get-started-with-cpp-build-insights?view=msvc-170)。
>
> WPA和vcperf相关安装可查看[这个](https://learn.microsoft.com/en-us/cpp/build-insights/tutorials/vcperf-and-wpa?view=msvc-170)和[这个](https://baijiahao.baidu.com/s?id=1666271161172135646&wfr=spider&for=pc)。

## 使用vcperf

使用vcperf后，我立刻发现有一个头文件占用了35秒之久，原因是这个头文件包含了很多其他头文件，且被很多源文件包含。因为没有使用预编译，这个头文件被包含多次，导致编译时间变得很长。

针对vcperf给出的每个文件的编译时间细节，我把刚刚的头文件加到了pch.h中，并优化了其他一些细节，最后成功将编译时间缩短到了17秒。

其中这个是使用预编译之前的图：

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/technology/no_pch_header.jpg)

这是使用预编译之后的图：

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/technology/pch_header.jpg)

## 结语

对于大工程，预编译是明显有必要的，目前很多编译器都支持，比如VC++，gcc，clang等。在多平台编译的讨论中，有些人采取的是windows使用预编译，在gcc上使用直接编译，因为gcc上好像提升不是很明显，这似乎也得益于gcc在多层包含、多次包含上可能会更快一点，不过gcc是否需要预编译还需看实践中的差异。

## 参考链接

- [善用预编译PCH文件提升编译速度](https://baijiahao.baidu.com/s?id=1666271161172135646&wfr=spider&for=pc)
- [Precompiled Headers in Header Files](https://stackoverflow.com/questions/11403211/precompiled-headers-in-header-files)
- [Handling stdafx.h in cross-platform code](https://stackoverflow.com/questions/1191248/handling-stdafx-h-in-cross-platform-code)
- [Visual C++ 'Force Includes' option](https://stackoverflow.com/questions/320723/visual-c-force-includes-option)
- [Precompiled header](https://en.wikipedia.org/wiki/Precompiled_header)
- [Get started with C++ Build Insights](https://learn.microsoft.com/en-us/cpp/build-insights/get-started-with-cpp-build-insights?view=msvc-170)
