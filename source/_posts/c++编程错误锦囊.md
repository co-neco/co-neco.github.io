---
title: c++编程错误锦囊
categories:
  - Technology
  - Development
date: 2021-10-19 20:13:41
tags: 
  - C++ Programming

---

## 1 基类需要定义虚析构函数

根据开发场景，继承类有两种情况：

- 继承类是别人写的，那么继承类可能会有析构函数，如果调用以下代码，那么继承类的析构函数不会被调用：

  ```cpp
  BaseClass* = new InheritedClass;
  delete BaseClass;
  ```

- 继承类是自己写的，开发者可能会觉得继承类不需要析构函数，因此可以不给基类加虚析构函数。但随着需求的变化，可能继承类添加了析构函数。如果开发者没同时给基类加虚析构函数，那么就会出问题。

最佳实践：基类应该总是定义虚析构函数，不管当前需析构函数是否是有用的。

> 注：
>
> - 如果该基类不需要多态析构（比如基类没有虚函数，或者基类本意不希望显式分配任何对象等），那么该基类的析构函数应该是protected且不是virtual的。
>
>   不过有一个特殊情况，如果在使用子类时，用到了unique_ptr，比如：
>
>   ```cpp
>   std::unique_ptr<BaseClass> b = std::make_unique<InheritedClass>();
>   ```
>
>   因为std::unique_ptr强制需要'std::unique_ptr\<BaseClass\>'里的BaseClass提供public的析构函数，因此以上语句会编译出错。具体原因可查看[这个答案](https://stackoverflow.com/a/59695222)。针对unique_ptr的这个限制，我尝试寻找过解决方法，比如[这个答案](https://stackoverflow.com/questions/56377634/protected-destructor-with-unique-ptr)，其中有一个是在基类添加 friend std::unique_ptr\<BaseClass\>。但正如`Peter`所说，std::unique_ptr\<BaseClass\>的用法只会调用基类的虚构函数(因为BaseClass的析构函数是non-virtual)。因此，针对这种特殊情况，我们可以采用protected的虚析构函数 + friend std::default_delete\<BaseClass\>。（virtual的原因是std::unique_ptr使用deleter时，能找到对应的子类析构函数，不过在shared_ptr中就不存在这种情况）。
>
>   关于何时不需要析构函数是virtual的，可参考[这个讨论](https://stackoverflow.com/questions/300986/when-should-you-not-use-virtual-destructors)中，‘sep’和‘andy’的回答。
>
> - 因为编译器默认会给类添加public且nonvirtual的析构函数，所以我们应该总显式定义析构函数

## 2 使用delete关键字删除特定类型

因为某些特殊原因，可能某个类的一个成员变量是void*，但该变量是指向一个类实例的，那么在使用delete时，需要指明这个成员变量的类型，否则delete不能正确调用类实例对应的析构函数，造成内存泄漏等问题：

```cpp
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

## 3 shared_ptr的参数是一个数组时，显示定义对应的释放操作

因为shared_ptr最终会使用delete关键字释放内容，所以如果内容是new分配的一个数组，那么程序将会出现问题。为避免这个问题，可以给shared_ptr具体的释放方法：

```cpp
std::shared_ptr<WCHAR>(new WCHAR[nLen * sizeof(WCHAR)]{ 0 }, std::default_delete<WCHAR[]>());
//释放方法：std::default_delete<WCHAR[]>()
//释放方法也可以写成一个lambda
```

在讨论中，`sysml`也给出了c++17的解决方法：

```cpp
std::shared_ptr<WCHAR[]>(new WCHAR[nLen * sizeof(WCHAR)]{ 0 });
```

这样使得代码看起来更加简洁。

## 4 类的构造函数初始化所有成员变量

因为release版本不会自动初始化类的成员变量，所以应对所有成员变量赋默认值。

> 注：STL的类会初始化（因为编译器生成的默认构造函数会初始化这些成员变量）

## 释放后的指针应该赋值为NULL或nullptr

```cpp
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

## 5 如果类有复制构造函数或复制赋值运算符的其中一个，那必须补齐另外一个

根据c++的 Law of The Big Three 规则（暂不考虑move语义），我们知道如果定义了以下其中一个，那么另外两个会被编译器隐式定义：

- 析构函数
- 复制构造函数
- 复制赋值运算符

因此，如果一个类有复制构造函数，并且没有重载复制赋值运算符，那么会出现隐患，这个类也是危险的类：

```cpp
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

```cpp
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

## 6 包含运算符的宏要用括号括起来

```cpp
#define MEM_BUFFER_NUMBER 2
#define MEM_BUFFER_SIZE (sizeof(PVOID) * MEM_BUFFER_NUMBER)
```

## 7 引用变量需要加&，即使是auto

```cpp
// A& GetA();
auto& A = GetA();
// 不是 auto A = GetA();
```

## 8 智能指针的合理使用

智能指针在C++中有几个，比如shared_ptr，unique_ptr，auto_ptr等，每一个都有各自的用途和其存在意义，因此开发中需要跟进实际场景，使用合适的智能指针。

根据我实际开发的场景，总结建议如下：

- 避免所有场景都使用shared_ptr。shared_ptr是功能最丰富的智能指针，大部分资源的自动分配与释放都可以用shared_ptr解决。但如果所有场景都使用shared_ptr，会存在如下弊端：

  - 掩盖设计：如果资源的主体是该资源唯一的拥有者，那么使用shared_ptr会掩盖这个背景，比如：

    ```cpp
    class A {
    public:
        A(){m_a = new std::string("aaa");}
        ~A(){delete m_a;}
    private:
        std::string* m_a;
    }
    //因为要管理m_a的分配和释放，改进后的A如下：
    class A {
    public:
    	A(){m_a = std::make_unique<std::string>("aaa");}    
    private:
        std::unique_ptr<std::string> m_a;
    }
    //通过使用unique_ptr，可以看出类A的实例a是唯一拥有m_a的主体，且实例a管理m_a的生命周期。
    //如果这里使用的是shared_ptr，那么当我们看类A的声明时，我们不知道m_a有这一层含义。
    ```

    > 注：
    >
    > 掩盖设计只是一个小点，影响更大的是随后的开发。因为掩盖设计会影响开发者对这部分代码的理解，使得这部分代码的设计在之后的开发中越来越模糊。而这带来的最明显的后果就是降低可维护性（这里的设计可以理解成某一个设计模式，或者一个设计场景）。
    >
    > 相反，如果使用unique_ptr，那么unique_ptr的限制会让开发者清楚资源的拥有者，提示开发者代码的设计目标（比如资源的唯一拥有者应该是谁，资源该如何分享，该返回原指针还是资源的引用），且能保证资源的生命周期。

  - 影响软件的性能：shared_ptr在资源的释放时机上比unique_ptr更晚。shared_ptr使得资源的拥有者是多个，只有最后一个拥有者释放该资源后，资源才会被释放。

  > 注：何时选择哪种智能指针请参考[这个回答](https://stackoverflow.com/a/7658089)。

- 给资源使用unique_ptr时，如果调用方(caller)想获取该资源，但不能控制其生命周期，那么返回的类型如下：

  - 如果该资源肯定存在，即不为nullptr，那么返回资源的引用

  - 如果该资源可能为nullptr，那么返回指向资源的指针

    ```cpp
    //接着class A的例子
    class A{
    //...
    // Return m_a
    public:
        //m_a肯定存在的情况
        std::string& GetA() {return *m_a.get();}
        //m_a可能为nullptr的情况
        std::string* GetA() {return m_a.get();}
    }
    ```

## windows平台字符集的处理

需要传输到网络的数据中，字符串应该均用utf-8编码。因为windows使用的是默认windows ANSI编码，所以字符串在传输中应该转为utf-8编码。

Windows平台在处理字符时，默认使用的代码页(code page)是CP_ACP，不是CP_UTF8。即windows平台默认的字符串可能与其他机器不兼容，其他机器解析会乱码，比如字符串包含中文时。

> 下面是MSDN的描述：
>
> **Note** The ANSI code pages can be different on different computers, or can be changed for a single computer, leading to data corruption. For the most consistent results, applications should use Unicode, such as UTF-8 or UTF-16, instead of a specific code page, unless legacy standards or data formats prevent the use of Unicode. If using Unicode is not possible, applications should tag the data stream with the appropriate encoding name when protocols allow it. HTML and XML files allow tagging, but text files do not.

另外，如果windows的系统语言是英语，那么windows本地的windows ANSI编码(CP_ACP)是不支持中文之类的。因此在这种情况下，需要先使用unicode字符集，然后再编码成utf-8。

> Windows提供了**MultiByteToWideChar**和**WideCharToMultiByte**这两个winapi用于多字节字符和unicode字符的转换。由于unicode只是一种字符的表示方式（用两个code point表示一个字符），并不存在编码，因此在使用上述的两个winapi需要注意：
>
> - **WideCharToMultiByte**的CodePage参数表示将unicode字符串转换成哪种编码格式的多字节字符。
> - **MultiByteToWideChar**的CodePage参数表示将哪种编码格式的多字节字符转换成unicode字符。如果这里提供的codePage错误，那么转换会成功，但结果是错误的。另外，如果多字节字符包含中文，但不是utf-8编码，比如是windows ANSI编码，那么编译的程序在中文系统是表示正确的，但是在英文系统就会乱码，因为英文系统的windows ANSI本地编码识别不了这些中文字符。

编程实践：

- 在工程开始的最初，就只使用unicode。只在显式需要的时候，再转换成utf-8编码的多字节字符（比如使用json时）。
- 可以使用一套代码，既支持多字节也支持unicode，在这两种字符集切换时保持windows ANSI的编码。只在显式需要的时候，再转换成utf-8编码的多字节字符。

