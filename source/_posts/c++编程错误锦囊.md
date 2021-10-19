---
title: c++编程错误锦囊
categories:
  - Technology
  - Development
date: 2021-10-19 20:13:41
tags: 
  - C++ Programming

---

## 存在虚函数的基类需要定义虚析构函数

如果基类有虚函数，那么继承类有两种情况：

- 继承类是别人写的，那么继承类可能会有析构函数，如果调用以下代码，那么继承类的析构函数不会被调用：

  ```c++
  BaseClass* = new InheritedClass;
  delete BaseClass;
  ```

- 继承类自己写的，开发者可能会觉得继承类不需要析构函数，因此可以不给基类加虚析构函数。但随着需求的变化，可能继承类添加了析构函数。如果开发者没同时给基类加虚析构函数，那么就会出问题。

> 注：为什么基类有虚函数，才要定义虚析构函数呢？原因是有虚函数，开发者才会用到多态的特性，使用基类指针代表继承类。

最佳实践：有虚函数的基类应该总是定义虚析构函数，不管当前需析构函数是否是有用的。

## 使用delete关键字删除特定类型

因为某些特殊原因，可能某个类的一个成员变量是void*，但该变量是指向一个类实例的，那么在使用delete时，需要指明这个成员变量的类型，否则delete不能正确调用类实例对应的析构函数，造成内存泄漏等问题：

```c++
class B {
    ...
};

class A {
public:
    A(){
        m_pointer = new B;
    }
    
    ~A(){
        //delete m_pointer;  --> wrong delete
        delete (B*)m_pointer;
    }
    
    void* m_pointer;
};
```

## shared_ptr的参数是一个数组时，显示定义对应的释放操作

因为shared_ptr最终会使用delete关键字释放内容，所以如果内容是new分配的一个数组，那么程序将会出现问题。为避免这个问题，可以给shared_ptr具体的释放方法：

```c++
std::shared_ptr<WCHAR>(new WCHAR[nLen * sizeof(WCHAR)]{ 0 }, std::default_delete<WCHAR[]>());
//释放方法：std::default_delete<WCHAR[]>()
//释放方法也可以写成一个lambda
```

## 类的构造函数初始化所有成员变量

因为release版本不会自动初始化类的成员变量，所以应对所有成员变量赋默认值。

## 释放后的指针应该赋值为NULL或nullptr

```c++
__try{
    PVOID p = VirtualAlloc(..., size, ...);
}
__finally{
    if (p != NULL){
        VirtualFree(p, ...);
        p = NULL;  // --> set p as NULL
    }
}

if (p != NULL){
    //...
}
```

## 如果类有复制构造函数或复制赋值运算符的其中一个，那必须补齐另外一个

根据c++的 Law of The Big Three 规则（暂不考虑move语义），我们知道如果定义了以下其中一个，那么另外两个会被编译器隐式定义：

- 析构函数
- 复制构造函数
- 复制赋值运算符

因此，如果一个类有复制构造函数，并且没有重载复制赋值运算符，那么会出现隐患，这个类也是危险的类：

```c++
/* wrong definition*/ 
class A{
public:
    A(){a = 1; b = new int;}
    ~A(){
        delete b;
    }
    
    A(const A& instance){
        this->a = instance.a;
        this->b = new int;
    }
    
    int a;
    int* b;
};

A a;    // a.b points to addr1
A b(a); // b.b points to addr2
b = a;  // b.b points to addr1 --> error
```

因为复制构造函数和重载的复制赋值运算符必须成对存在，对于move语义的两个方法也是一样：

```c++
class A{
public:
    A(){a = 1; b = new int;}
    ~A(){
        delete b;
    }
    
    A(const A& instance){
        Copy(instance);
    }
    A& operator=(const A& instance){
        Copy(instance);
        return *this;
    }
    
    // move semantics
    A(A&& instance){...}
    A& operator=(A&& instance){...}
    
private:
    void Copy(const A& instance){
        this->a = instance.a;
        this->b = new int;
    }
    
public:
    int a;
    int* b;
};
```

## 包含运算符的宏要用括号括起来

```c++
#define MEM_BUFFER_NUMBER 2
#define MEM_BUFFER_SIZE (sizeof(PVOID) * MEM_BUFFER_NUMBER)
```

