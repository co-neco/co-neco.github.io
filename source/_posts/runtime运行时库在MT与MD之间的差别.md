---
title: runtime运行时库在MT与MD之间的差别
categories:
  - Technology
  - Development
date: 2021-08-05 20:54:42
tags: 
 - MT
 - MD
 - Runtime
 - 运行时
 - VS
---

### VS Runtime(运行时)库的介绍

运行时库提供了很多变量（包括常量），还有很多类函数，比如字符串处理、输入与输出等。它们可以被静态编译到可执行文件（EXE或DLL），也可以被动态加载。

详细的说明可参考[C runtime library (CRT) reference - Microsoft Docs](https://docs.microsoft.com/en-us/cpp/c-runtime-library/c-run-time-library-reference)。关于用到的库可参考[C runtime (CRT) and C++ Standard Library (STL) `.lib` files](https://docs.microsoft.com/en-us/cpp/c-runtime-library/crt-library-features?view=msvc-160)。

本文重点阐述运行时库在MT和MD之间的区别。

### 运行时库的区别

不管编译DLL还是EXE，都可以在VS中设置运行时库。

> 设置路径为*工程属性->Configuration Properties->C/C++->Code Generation->Runtime Library*。

运行时库分4类：

- MTd（Multi-threaded Debug）
- MDd（Multi-threaded Debug DLL）
- MT (Multi-threaded)
- MD (Multi-threaded DLL)

其中最后带d的为Debug版本的运行时库，不带d的为Release版本的运行时库。MTd和MT的T代表静态库，MDd和MD的D代表动态库。

也就是说采用MTd或MT，运行时库会被编译进EXE或DLL里；而MDd或MD的情况下，在EXE启动或DLL被加载时，运行时库会作为DLL被动态载入。

因为DLL和EXE编译时采用MT(d)或MD(d)的结果是一样的，所以这里以EXE编译时采用MT或MD为例。

### EXE编译时采用MT运行时库

- EXE编译时依赖了其他库，这个库是静态库（x.lib）

  在EXE采取MT运行时库时，静态库(x.lib)的编译也必须是MT。因为静态库的原因，EXE只需要把自己需要的代码从静态库(x.lib)提取出来就行，不考虑静态库里的运行库。所以这种情况下EXE和静态库使用的运行时库是同一套代码，都是EXE的运行时库。

- EXE编译时依赖了其他库，这个库是动态库（x.dll）

  在EXE采取MT运行时库时，动态库(x.dll)的编译也必须是MT。因为是动态库，EXE在加载动态库时，是将其全部代码(包括一份运行时库代码)加载进了EXE进程空间，这样EXE在运行时就包含了两套运行时库代码，一个是动态库的，一个是EXE的。

  > 注：虽然EXE和DLL会用各自的运行时库，但它们用的都是进程默认堆(PEB->ProcessHeap)，不存在EXE和DLL用的堆不一致的情况（网上有说使用的堆不一样，这种说法是错误的）。

### EXE编译时采用MD运行时库

不管EXE依赖的其他库是静态库还是动态库，它们都必须采用MD来编译。这种情况下编译出来的EXE和DLL（或EXE和LIB）都依赖MD运行时库（即VCRUNTIMExx.dll、MSVCPxx.dll、ucrtbase.dll）。因为都依赖MD运行时库，所以EXE和DLL（或EXE和LIB）用的是同一套运行时库。

### EXE依赖DLL，EXE和DLL都采用MT时可能会遇到的错误

根据上一节的描述，这种情况下，EXE和DLL会用各自的运行时库，这时会导致一种错误，如下代码所示：

```c
// In EXE test.cpp

#include "dll.h"
int main(){
    std::string str = GetString();
    std::cout << str << "\n";
    return 0;
}
```

```c
// In DLL dll.h
#ifndef FUNC_TEST
#define FUNC_TEST extern "C" __declspec(dllimport)
#endif
FUNC_TEST std::string GetString();

// In DLL dll.cpp
#define FUNC_TEST extern "C" __declspec(dllexport)
#include "dll.h"
std::string GetString() {
    std::string str("hello world");
    return str;
}
```

以上代码会导致如下错误：

```c
//assertion failed!
__acrt_first_block == header 
```

这个问题的成因请看下一节。

### 运行时库的堆管理机制

即使运行时库有两份，这两份代码用的堆都是进程默认堆。

运行时库管理堆采用链表的方式，这里以std::string(x86)为例。当定义一个std::string变量（初始值为“hello worldaaaaa”，长度为0x10）时，运行时库会为该字符串从默认进程堆分配堆块。

> 长度超过0x10，就会分配堆块来存储字符串，若小于0x10，则存在栈上。

#### 链表管理机制

1. 重要变量

   运行时库管理堆时，有三个比较重要的变量

    - __acrt_heap，都指向进程默认堆
    - __acrt_first_block指向最新被分配的堆块（初始值为nullptr）
    - __acrt_last_block指向最久被分配的堆块（初始值为nullptr）

2. 算法

   - 第一次分配堆块A后

     ![分配堆块A](https://gitee.com/co-neco/pic_bed/raw/master/typora/image-20210805235444099.png)

   - 第二次分配堆块B后

     ![分配堆块B](https://gitee.com/co-neco/pic_bed/raw/master/typora/image-20210805235657331.png)

   - 第三次分配堆块C后

     ![分配堆块C](https://gitee.com/co-neco/pic_bed/raw/master/typora/image-20210805235933752.png)

   - 释放堆块C后，情况如“第二次分配堆块B后”。

   > 根据以上算法，每个运行时库会管理各自的堆块(虽然都是从进程默认堆分配的)，所以EXE和DLL的运行时库都分别有以上三个重要变量。一般情况下，每个运行时库的\_\_acrt_first_block都不相等，__acrt_last_block同理。

3. 安全检测

   在释放堆块时，运行时库会检测当前释放的堆块是否与当前运行时库的\_\_acrt_first_block相等，如果相等，则继续释放；如果不相等，则断言失败。
   
   观察上一节的代码，因为DLL返回的str字符串在EXE的代码空间里（领空）被释放，所以EXE的运行时库会去检查字符串的堆块是否与EXE运行时库的\_\_acrt_first_block相等。但由于这个堆块是DLL的运行时库分配的，所以该堆块与DLL运行时库的\_\_acrt_first_block相等，与EXE运行时库的\_\_acrt_first_block不相等。
   
   如果出现不相等的情况，在Debug模式会弹出对话框，这就是上一节出现错误的原因。由于Release版本去掉了断言，所以之后可能会产生更严重的后果，因为两个运行时库的堆管理出现了交叉。

### 解决方法

根据前两节的描述，问题在于一个运行时库分配堆块，另一个运行时库释放堆块。那么解决的方法就是在传递参数或返回参数时，通过指针或引用的方式，直接传递，防止中间的类复制（调用复制构造函数）。

### 一个应用存在多个运行时库存在的问题

在MSDN发现了很值得一读的一节，这里直接献上原汁原味的原文：

{% blockquote MSDN https://docs.microsoft.com/en-us/cpp/c-runtime-library/crt-library-features?view=msvc-160 C runtime (CRT) and C++ Standard Library %}

Every executable image (EXE or DLL) can have its own statically linked CRT, or can dynamically link to a CRT. The version of the CRT statically included in or dynamically loaded by a particular image depends on the version of the tools and libraries it was built with. A single process may load multiple EXE and DLL images, each with its own CRT. Each of those CRTs may use a different allocator, may have different internal structure layouts, and may use different storage arrangements. This means allocated memory, CRT resources, or classes passed across a DLL boundary can cause problems in memory management, internal static usage, or layout interpretation. For example, if a class is allocated in one DLL but passed to and deleted by another, which CRT deallocator is used? The errors caused can range from the subtle to the immediately fatal, and therefore direct transfer of such resources is strongly discouraged.

​	

You can avoid many of these issues by using Application Binary Interface (ABI) technologies instead, as they are designed to be stable and versionable. Design your DLL export interfaces to pass information by value, or to work on memory that is passed in by the caller rather than allocated locally and returned to the caller. Use marshaling techniques to copy structured data between executable images. Encapsulate resources locally and only allow manipulation through handles or functions you expose to clients.

​	

It's also possible to avoid some of these issues if all of the images in your process use the same dynamically loaded version of the CRT. To ensure that all components use the same DLL version of the CRT, build them by using the **`/MD`** option, and use the same compiler toolset and property settings.

​	

Be careful if your program passes certain CRT resources across DLL boundaries. Resources such as file handles, locales, and environment variables can cause problems, even when using the same version of the CRT. For more information on the issues involved and how to resolve them, see [Potential Errors Passing CRT Objects Across DLL Boundaries](https://docs.microsoft.com/en-us/cpp/c-runtime-library/potential-errors-passing-crt-objects-across-dll-boundaries?view=msvc-160).

{% endblockquote %}

### 参考

- [C runtime (CRT) and C++ Standard Library (STL) .lib files](https://docs.microsoft.com/en-us/cpp/c-runtime-library/crt-library-features?view=msvc-160)

