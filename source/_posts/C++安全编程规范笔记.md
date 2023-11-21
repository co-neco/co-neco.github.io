---
title: C++安全编程规范笔记
categories:
  - Technology
  - Development
date: 2023-11-21 14:07:26
tags:
  - C++
  - secure coding
---

在学习`SEI CERT C++ Coding Standard 2016 edition`时，对于不能理解的点做了一些探索，本文是相关的记录。

> 该书的下载链接：[SEI CERT C++ Coding Standard](https://resources.sei.cmu.edu/downloads/secure-coding/assets/sei-cert-cpp-coding-standard-2016-v01.pdf)。

## 在构造或析构函数中不要调用虚函数

根据C++规范，常见的错误如下：

```cpp
struct B {
 B() { seize(); }
 virtual ~B() { release(); }
protected:
 virtual void seize();
 virtual void release();
};
struct D : B {
 virtual ~D() = default;
protected:
 void seize() override {
 B::seize();
 // Get derived resources...
 }
 void release() override {
 // Release derived resources...
 B::release();
 }
};
```

在实例化D类时，B类的构造函数会先调用。B类在构造函数中调用了seize虚构函数，此时的D的实例还没有初始化，B类构造函数调用的将是B::seize，而不会调用D::seize。析构函数也同理，在B的析构函数中尝试调用virtual的release，本意是调用D::release来释放，但实际调用的是B::release。

这样的结果是D类实例在构造，资源没有获取(seize)，D类实例在析构时，资源也没有释放（release）。

如果seize和release是纯虚函数，将会导致未定义行为。不过由于这种情况下程序不能编译通过（因为B类没有seize和release的实现），因此这种情况可以在程序运行前被处理掉。

不过C++规范中还阐述了另一种未定义行为，其原文如下：

The C++ Standard, [class.cdtor], paragraph 4 [ISO/IEC 14882-2014], states the following：

> Member functions, including virtual functions, can be called during construction or 
> destruction. When a virtual function is called directly or indirectly from a constructor or 
> from a destructor, including during the construction or destruction of the class’s non
> static data members, and the object to which the call applies is the object (call it x) 
> under construction or destruction, the function called is the final overrider in the 
> constructor’s or destructor’s class and not one overriding it in a more-derived class. **If the** 
> **virtual function call uses an explicit class member access and the object expression** 
> **refers to the complete object of x or one of that object’s base class subobjects but not x**
> **or one of its base class subobjects, the behavior is undefined.**

最后加粗的一句话读了很多遍都没理解，不过从`13 revs AndreyT`的回答中，理解的背后的原因。

> 详情可参考: [C++ constructors: why is this virtual function call not safe?](https://stackoverflow.com/a/11378023/8717240)。

从可视化的角度来解释,可参考如下的一张图

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/technology/cpp/virfunc_in_cons_violation.jpg)

该图是一张继承图的大致关系，J继承自H和I，H和I的基类都有X类。

简单来说，在H的构造函数中，可以调用椭圆以内的虚函数（比如A、E、B的虚函数），但不能调用椭圆以外的虚函数。

假如X有一个名叫func的纯虚函数，这里给H的构造函数传入了一个参数，该参数是指针，指向G类的实例，那么此时调用该参数的func函数将会导致“未定义的行为”。

现在再来回味那句话：

- "If the virtual function call uses an explicit class member access"

  这里的virtual function call是func纯虚函数，explicit class member是G实例。

- "the object expression refers to the complete object of x or one of that object’s base class subobjects"

  这里的"object expression"指的是G类的实例，complete object指的是J实例。

- "but not x or one of its base class subobjects"

  这里的x是J实例，one of its base class subobjects是H实例。

> 关于这句话的描述可参考：https://stackoverflow.com/a/11377756。

## 不要在析构函数或内存释放函数拋异常

这一点的详情看参考书中的2.8节，这一小节遇到的疑点是如下的C++规范：

> ```cpp
> class SomeClass {
>  Bad bad_member;
> public:
>  ~SomeClass()
>  try {
>  // ...
>  } catch(...) {
>  // Handle the exception thrown from the Bad destructor.
>  }
> };
> ```
>
> The currently handled exception is rethrown if control reaches the end of a handler of the function-try-block of a constructor or destructor.

为什么走到构造或析构函数的catch块末尾，会重新拋异常呢？

在[这篇文章](http://www.gotw.ca/gotw/066.htm)中，详细阐述了为什么需要重新拋异常的原因，这里大致总结一下：

类实例的生命周期从构造函数成功执行、顺利返回时开始，从进入析构函数时结束。简单来说，如果在构造函数的try中拋异常，即没有正常返回，那么该实例对象是不存在的，那么为了避免调用者使用该实例（因为该实例不存在，声明周期都没有开始），所以就不能忽略抛出的异常，必须再次抛出。析构函数同理，由于进入析构函数时，类实例的声明周期就已经结束了，那么析构函数抛出异常时，该实例已经不存在了，因此只有拋异常。
