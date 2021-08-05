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

在VS编译程序时，我们指定了入口函数。但这不是真正的入口函数，MSVC会提供真正的入口函数，对应关系举例如下：

- main -> mainCRTStartup
- winMain -> _WinMainCRTStartup
- DllMain -> _DllMainCRTStartup

我们可以暂且将mainCRTStartup到main之间的代码理解为VS编译时插入的运行时库。

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

不管EXE依赖的其他库是静态库还是动态库，它们都必须采用MD来编译。这种情况下编译出来的EXE和DLL（或EXE和LIB）都依赖MD运行时库（即VCRUNTIMExx.dll和MSVCPxx.dll）。因为都依赖MD运行时库，所以EXE和DLL（或EXE和LIB）用的是同一套运行时库。

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

    - __acrt_heap，都使用进程默认堆
    - __acrt_first_block指向最新被分配的堆块（初始值为nullptr）
    - __acrt_last_block指向最久被分配的堆块（初始值为nullptr）

2. 算法

   - 第一次分配堆块A后

     ![分配堆块A](image-20210805235444099.png)

   - 第二次分配堆块B后

     ![分配堆块B](image-20210805235657331.png)

   - 第三次分配堆块C后

     ![分配堆块C](image-20210805235933752.png)

   - 释放堆块C后，情况如“第二次分配堆块B后”。

   > 根据以上算法，每个运行时库会管理各自的堆块(虽然都是从进程默认堆分配的)，所以EXE和DLL的运行时库都分别有以上三个重要变量。一般情况下，每个运行时库的\_\_acrt_first_block都不相等，__acrt_last_block同理。

3. 安全检测

   在释放堆块时，运行时库会检测当前释放的堆块是否与当前运行时库的\_\_acrt_first_block相等，如果相等，则继续释放；如果不相等，则断言失败。
   
   观察上一节的代码，因为DLL返回的str字符串在EXE的代码空间里（领空）被释放，所以EXE的运行时库会去检查字符串的堆块是否与EXE运行时库的\_\_acrt_first_block相等。但由于这个堆块是DLL的运行时库分配的，所以该堆块与DLL运行时库的\_\_acrt_first_block相等，与EXE运行时库的\_\_acrt_first_block不相等。
   
   如果出现不相等的情况，在Debug模式会弹出对话框，这就是上一节出现错误的原因。由于Release版本去掉了断言，所以之后可能会产生更严重的后果，因为两个运行时库的堆管理出现了交叉。

