---
title: COM学习笔记
categories:
  - Technology
  - Development
date: 2022-02-13 23:06:16
tags:
  - COM
  - tutorial
---

这是一篇关于COM基础开发的笔记，主要讲`in-process dll`和`out-of-process server`开发时，值得注意的一些细节，完整的代码请参考[github](https://github.com/co-neco/COM_study)。

> 注：
>
> - 该工程目前只配置了Debug x64位。
> - 建议读者看本文前，先阅读`Windows 10 System Programming_part2`的第二十一章，学习开发COM的基础知识。本文可当做开发COM的细节指导。

## 背景

最近看了`Pavel Yosisofich`的`Windows 10 System Programming_part2`这本书，并实践了第二十一章：COM，于是有了本文。

## COM简述

COM是`Component Object Model`的缩写，它提供了二进制级别的接口，而c/c++提供的是源代码级别的接口。

COM的诞生是为了解决c/c++接口存在的诸多不便，以下举一个简单的例子。

我们使用一个DLL时（如果是我们开发的），会导入它的lib，加上dll的头文件（包含导出函数）。比如这个DLL有一个导出函数GetOneString，用户端调用如下：

```c
//dll.h
extern "c" __declspec(dllimport) std::string GetOneString();

// client's main.cpp
#include "dll.h"
#pragma comment(lib, "dll.lib")
int main(){
    std::string a = GetOneString();
    std::cout << a << "\n";
    return 0;
}
```

这里，我们从DLL获取了一个std::string类型的变量，当main函数退出时，`a`这个变量会被释放，如果这个变量表示的字符串足够长，那么`a`变量持有的堆块指针也会被释放。这时你的程序可能就崩了。因为DLL可能管理着自己的堆分配，然后用户端也管理着自己的堆分配。`a`变量析构时会用用户端的运行时库来释放DLL管理的堆块。详细的描述可参考[runtime运行时库在MT与MD之间的差别](https://conecoy.cn/Technology/Development/runtime%E8%BF%90%E8%A1%8C%E6%97%B6%E5%BA%93%E5%9C%A8MT%E4%B8%8EMD%E4%B9%8B%E9%97%B4%E7%9A%84%E5%B7%AE%E5%88%AB/)。

`Windows 10 System Programming_part2`书中也有一个例子，其大意是在更新DLL二进制文件时，用户端无感知，在栈上分配的类实例大小与以前的不匹配，从而可能导致崩溃。

> 详情可参考书中的第二十一章。

而COM是二进制级别的接口，用户端是看不到DLL的实现的，只能看到DLL的接口，因此以上的问题都可以规避。比如第一个例子，COM规定客户端与服务端使用字符串时，必须使用HSTRING类型。因为不使用std::string了，自然第一个例子的问题就不存在了。关于第二个例子，因为客户端看不到服务端代码的实现，所以从服务端返回类实例时，客户端只能获取到一个指针，这样就不存在类实例在客户端栈上分配的情况了。

## In-process DLL 服务端的细节

### In-process DLL的实现

关于COM开发的概念知识，这里就不再赘述了，对COM不了解的读者可参考`Windows 10 System Programming_part2`的第二十一章。

通过DLL方式提供功能的服务端是比较简单，容易理解的。它包含三个类，一个工厂类，一个接口，一个实现接口的类：

- RPNCalculator.h
- RPNCalculatorInterfaces.h
- RPNCalculatorFactory.h

为了注册DLL，DLL需要自己实现以下三个函数（详情参考dllmain.cpp）：

- DllGetClassObject
- DllRegisterServer
- DllUnregisterServer

### 客户端对DLL服务的调用

客户端的大致代码框架如下：

```c
auto hr = CoInitialize(NULL);
//...
CoUninitialize();
```

指定实现接口的类的CLSID时，一般有两种方法：

```c
CComPtr<IRPNCalculator> spCalc;
//hr = spCalc.CoCreateInstance(__uuidof(RPNCalculator));
hr = spCalc.CoCreateInstance(CLSID_RPNCalculator);
if (FAILED(hr)) {
    std::cout << "last error" << (LPVOID)hr << "\n";
    return -1;
}
```

- 通过\_\_uuidof的方式

  这种方式需要在DLL接口的头文件中声明类的CLSID：

  ```c
  class __declspec(uuid("D4B830A5-7DFC-4C81-9268-8BB0BEA7CACE")) RPNCalculator;
  ```

- 通过定义CLSID_RPNCalculator变量的方式（类型是GUID）

  ```c
  DEFINE_GUID(CLSID_RPNCalculator,
  	0xd4b830a5, 0x7dfc, 0x4c81, 0x92, 0x68, 0x8b, 0xb0, 0xbe, 0xa7, 0xca, 0xce);
  ```

  这种方式需要注意的是，客户端在包含文件时，应该如下：

  ```c
  // Come first, initguid.h has a INITGUID macro, which assigns 
  // DEFINE_GUID a command to define CLSID_RPNCalculator variable
  #include <initguid.h> 
  
  #include <Windows.h>
  #include <stdio.h>
  
  // cguid.h comes before any atl*.h header to get rid of no difinition error of GUID_NULL
  #include <cguid.h>
  
  #include <atlcomcli.h>
  
  #include <iostream>
  ```

## Out-of-process EXE server（local server）

关于如何写EXE Server，`Windows 10 System Programming_part2`书中并没有阐述，于是我在网上搜索，不过相关的资料是出奇的少。。。。最后几经周折，我参考了`COM技术内幕———微软组件对象模型` 书中的描述，完成了EXE Server的实验。

因为客户端和服务端在不同的进程里，因此存在跨进程的交互。为了统一地、标准地、简洁地处理这个场景，COM使用了proxy and stub（代理和残根）。由于`out-of-process`和`in-process`在代码上没有多大变化，这里会重点描述新增的操作。

### 1 添加IDL文件

IDL是`Interface Deginition Language`的缩写，其作用是通过微软的MIDL编译器生成接口类，便于跨平台（比如生成类型库，在c++、C#等不同的平台运行）、简化接口编写（比如代理和残根代码的自动化生成，在out-of-process EXE server的情况下，代理/残根的DLL是必需的），例子如下：

```c
import "unknwn.idl";

[
	object,
	uuid("F24C4FC4-3667-421D-A144-0AC0DF90D0AF"),
	helpstring("Calculator interface"),
	pointer_default(unique)
]
interface IRPNCalculator : IUnknown
{
	HRESULT push([in] double value);
	HRESULT pop([out] double* value);
	HRESULT add();
	HRESULT subtract();
};
```

> 如果没有proxy/stub的DLL，那么在客户端调用CoCreateInstance时，由于参数在跨进程的传输中没有定义传输方式（比如变量是输出参数还是输入参数），服务端收到的接口类GUID会是错误的，即不是CoCreateInstance指定的GUID。（在win10上测试是这样的）

> 关于IDL的语法请参考MSDN或`COM技术内幕`一书。

### 2 用MIDL编译IDL文件

运行VS的命令行，执行以下命令：

```bash
midl idl-file-name.idl
```

以上命令会生成代理/残根需要的所有代码（代理和残根可以自己实现，MIDL提供默认的实现）。生成的文件包括：

- XX.h: 包含接口的定义
- XX_i.c: 包含接口的GUID变量
- XX_p.c: 包含代理和残根的代码实现
- dlldata.c: 提供DLL所必需的导出函数（代理和残根的DLL所需要的，用于在注册表注册自己，注意只会生成一个DLL，这个DLL包含了代理和残根的实现）

### 3 编写Makefile，生成DLL

```makefile
all: midl app
.PHONY: all

PROXYSTUBOBJS = dlldata.obj \
				CalculatorTypeInfo_p.obj \
				CalculatorTypeInfo_i.obj

PROXYSTUBLIBS = kernel32.lib \
				rpcns4.lib \
				rpcrt4.lib \
				uuid.lib
# rpcndr.lib   -> rpcndr.lib is deprecated

midl:
# generate all parts(headers and source files) that our proxy dll need
	midl CalculatorTypeInfo.idl

app: $(PROXYSTUBOBJS) proxy_stub.def 
# generate proxy.dll used for proxy and stub.
	link /dll /out:proxy.dll /def:proxy_stub.def \
		$(PROXYSTUBOBJS) $(PROXYSTUBLIBS)
# regsvr32 by default writes registry configurations to HKLM/Software/CLSID
# , and the operation need administrator privilege.
# Therefore, you should run a cmd with administrator privilege.
	regsvr32 /s proxy.dll 

dlldata.obj: dlldata.c
	cl /c /DWIN32 /DREGISTER_PROXY_DLL dlldata.c

CalculatorTypeInfo_p.obj: CalculatorTypeInfo_p.c
	cl /c /DWIN32 /DREGISTER_PROXY_DLL CalculatorTypeInfo_p.c

CalculatorTypeInfo_i.obj: CalculatorTypeInfo_i.c
	cl /c /DWIN32 /DREGISTER_PROXY_DLL CalculatorTypeInfo_i.c

clean:
	del *.obj *.exp *.lib
```

注意`REGISTER_PROXY_DLL`这个宏，这个宏会自动生成DLL必需的导出函数。另外，makefile里有一行命令：

```bash
regsvr32 /s proxy.dll 
```

这行命令会将代理/残根的DLL(proxy.dll)注册到注册表中，这样客户端就可以像`in-process DLL`正常使用服务了。

### 4 客户端对服务的调用

包含MIDL生成的XX.h和XX_i.c文件，由于客户端还需要实现接口的类的CLSID，因此我们需要在XX_i.c文件中加入对应的CLSID，如下：

```c
MIDL_DEFINE_GUID(IID, CLSID_RPNCalculator,0xd4b830a5, 0x7dfc, 0x4c81, 0x92, 0x68, 0x8b, 0xb0, 0xbe, 0xa7, 0xca, 0xce);
```

另外，因为MIDL生成的文件已包含了一些关于GUID的头，之前在`in-process DLL`添加的`initguid.h`和`cguid.h`头文件就不需要包含了。