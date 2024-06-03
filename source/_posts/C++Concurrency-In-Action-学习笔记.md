---
title: C++ Concurrency In Action 学习笔记
categories:
  - Technology
  - Development
date: 2024-01-26 11:24:43
tags:
  - C++
  - Concurrency programming
  - atomic order
---

## Release ordering

对std::memory_order_relaxed内存顺序的例子（list 5.6）产生了疑问，以下做一个记录。

### 前置知识

- 同一个线程中，对不同变量的修改是有确定顺序的

  ```cpp
  int x,y;
  x = 0;
  y = 1;
  ```

  x变量的修改肯定发生在y变量的修改之前。

### 内存顺序选项

C++中有6个内存顺序选项(memory order options)，分别是memory_order_relaxed, memory_order_consume, memory_order_acquire, memory_order_release, memory_order_acq_rel，和 memory_order_seq_cst。

分为三组：

- memory_order_relaxed
- memory_order_release，memory_order_acquire
- memory_order_seq_cst

> 因为memory_order_consume不推荐使用，就不说明了。

#### Sequentially consistent ordering

std::memory_order_seq_cst，所有对原子变量的操作都是有确定的顺序的。

```cpp
#include <atomic>
#include <thread>
#include <assert.h>
std::atomic<bool> x,y;
std::atomic<int> z;
void write_x()
{
 x.store(true,std::memory_order_seq_cst); 
}
void write_y()
{
 y.store(true,std::memory_order_seq_cst); 
}
void read_x_then_y()
{
 while(!x.load(std::memory_order_seq_cst));
 if(y.load(std::memory_order_seq_cst)) 
 ++z;
}
void read_y_then_x()
{
 while(!y.load(std::memory_order_seq_cst));
 if(x.load(std::memory_order_seq_cst)) 
 ++z;
}
int main()
{
 x=false;
 y=false;
 z=0;
 std::thread a(write_x);
 std::thread b(write_y);
 std::thread c(read_x_then_y);
 std::thread d(read_y_then_x);
 a.join();
 b.join();
 c.join();
 d.join();
 assert(z.load()!=0); 
}
```

虽然x和y变量的修改在不同的线程，因为x和y的内存顺序选项是memory_order_seq_cst，所以x和y变量的修改顺序对于所有线程都是确定的。

即在read_x_then_y中，如果y是false，那么必定有x的修改在y的修改之前，这样read_y_then_x中，z肯定会自增。

#### Relaxed ordering

memory_order_relaxed，原子变量之间的操作没有同步关系。对同一个原子变量的操作之间是有确定顺序的，但对其他的线程就没有确定的顺序了。对于memory_order_relaxed，只有一个是保证的，即同一个线程中，对同一个原子变量的访问顺序是不变的。

```cpp
#include <atomic>
#include <thread>
#include <assert.h>
std::atomic<bool> x,y;
std::atomic<int> z;
void write_x_then_y()

{
 x.store(true,std::memory_order_relaxed); 
 y.store(true,std::memory_order_relaxed); 
}
void read_y_then_x()
{
 while(!y.load(std::memory_order_relaxed)); 
 if(x.load(std::memory_order_relaxed)) 
 ++z;
}
int main()
{
 x=false;
 y=false;
 z=0;
 std::thread a(write_x_then_y);
 std::thread b(read_y_then_x);
 a.join();
 b.join();
 assert(z.load()!=0); 
}
```

在write_x_then_y线程中，原子变量x和y的内存访问选项是std::memory_order_relaxed，所以x和y没有确定的修改顺序。

在read_y_then_x线程中，对x和y都是第一次访问，且x和y的内存访问选项是std::memory_order_relaxed，所以这里x和y的值没有确定的关系，x和y的值可能是false，也可能是true。

#### Acquire_release ordering

Acquire_release比relaxed要好一点，因为它多了一点，对一个原子变量的修改和访问是有同步关系的。

```cpp
#include <atomic>
#include <thread>
#include <assert.h>
std::atomic<bool> x,y;
std::atomic<int> z;
void write_x_then_y()
{
 x.store(true,std::memory_order_relaxed);  <-- 1
 y.store(true,std::memory_order_release);  <-- 2
}
void read_y_then_x()
{
 while(!y.load(std::memory_order_acquire)); <-- 3
 if(x.load(std::memory_order_relaxed))      <-- 4
 ++z;
}

int main()
{
 x=false;
 y=false;
 z=0;
 std::thread a(write_x_then_y);
 std::thread b(read_y_then_x);
 a.join();
 b.join();
 assert(z.load()!=0); 
}
```

这里，2和3是同步的，即3必定在2之后。又由于x和y变量的修改在同一个线程里，所以2在1之后。然后4在3之后，因此4在1之后，所以最后x为true。

### 关于Relaxed ordering的疑问

```cpp
#include <thread>
#include <atomic>
#include <iostream>
std::atomic<int> x(0),y(0),z(0); 
std::atomic<bool> go(false); 
unsigned const loop_count=10;
struct read_values
{
 int x,y,z;
};
read_values values1[loop_count];
read_values values2[loop_count];
read_values values3[loop_count];
read_values values4[loop_count];
read_values values5[loop_count];
void increment(std::atomic<int>* var_to_inc,read_values* values)
{
 while(!go) 
 std::this_thread::yield();
 for(unsigned i=0;i<loop_count;++i)
 {
 values[i].x=x.load(std::memory_order_relaxed);
 values[i].y=y.load(std::memory_order_relaxed);
 values[i].z=z.load(std::memory_order_relaxed);
 var_to_inc->store(i+1,std::memory_order_relaxed); 
 std::this_thread::yield();
 }
}
void read_vals(read_values* values)
{
 while(!go) 
 std::this_thread::yield();
 for(unsigned i=0;i<loop_count;++i)
 {
 values[i].x=x.load(std::memory_order_relaxed);
 values[i].y=y.load(std::memory_order_relaxed);
 values[i].z=z.load(std::memory_order_relaxed);
 std::this_thread::yield();
 }
}
void print(read_values* v)
{
 for(unsigned i=0;i<loop_count;++i)
 {
 if(i)
 std::cout<<",";
 std::cout<<"("<<v[i].x<<","<<v[i].y<<","<<v[i].z<<")";
 }
 std::cout<<std::endl;
}

int main()
{
 std::thread t1(increment,&x,values1);
 std::thread t2(increment,&y,values2);
 std::thread t3(increment,&z,values3);
 std::thread t4(read_vals,values4);
 std::thread t5(read_vals,values5);
 go=true; 
 t5.join();
 t4.join();
 t3.join();
 t2.join();
 t1.join();
 print(values1); 
 print(values2);
 print(values3);
 print(values4);
 print(values5);
}
```

书中描述这个程序的可能输出是这样的：

```cpp
(0,0,0),(1,0,0),(2,0,0),(3,0,0),(4,0,0),(5,7,0),(6,7,8),(7,9,8),(8,9,8),(9,9,10)
(0,0,0),(0,1,0),(0,2,0),(1,3,5),(8,4,5),(8,5,5),(8,6,6),(8,7,9),(10,8,9),(10,9,10)
(0,0,0),(0,0,1),(0,0,2),(0,0,3),(0,0,4),(0,0,5),(0,0,6),(0,0,7),(0,0,8),(0,0,9)
(1,3,0),(2,3,0),(2,4,1),(3,6,4),(3,9,5),(5,10,6),(5,10,8),(5,10,10),(9,10,10),(10,10,10)
(0,0,0),(0,0,0),(0,0,0),(6,3,7),(6,5,7),(7,7,7),(7,8,7),(8,8,7),(8,8,9),(8,8,9)
```

这里观察values1和values2两个数组，线程1修改x变量，线程2修改变量。

由于线程1，2，3都是单独自增同一个变量，内存顺序选项是std::memory_order_relaxed，因此t1能看到x变量从0递增到10。

观察values1的(5,7,0)，可理解为x自增为5的时候，y的变量已经自增到7了；观察values2的(8,5,5)，可理解为y自增为5的时候，x的变量已经自增到8了。也就是说y变量自增的比x变量慢，但values1的(5,7,0)却不是，这样似乎就矛盾了。如果x为5的时候，y为7，那y为5的时候，x怎么可能为8呢？看似矛盾的点其实有一个问题，因为以上结论是从两个角度观察而得出的，既有线程1的视角，又有线程2的视角。而memory_order_relaxed代表每个线程看到的顺序可以是不同的，所以线程1看y变量的修改和线程2看x变量的修改是独立的，分开的，没有关系的，只需要遵循线程1看到的y值是大于等于之前的y值即可。

至于以上的矛盾，要怎么用一种可能执行来解释，其实这是没有必要的，因为这个输出可能并不代表它的真实运行结果，因为编译器只需要保证程序的输出符合C++标准规定的限制条件。就比如const变量是无法修改的，但可以通过异常的语句来修改对应的变量，使得变量的地址处保存了更新的值，但如果程序之后再使用这个const变量，编译器仍会使用const变量原来的值，因为编译器知道它是常量，在给寄存器赋值的时候，直接使用了常量的值，而不是const变量地址处的值。

### 2024/06/03 更新

在学习完7.2.5小节之后，终于明白了原因。假设y的更新比x快，即values1的(5,7,0)成立，在values2的(8,5,5)也可以成立。因为虽然y的值此时是5，但x的值的修改在另外的线程，且是relaxed的内存顺序，所以读取x的值时，可以在x更新到8,9,10都行，就因为没有happens-before关系。

参考7.2.5小节的代码，else分支的`delete ptr`语句需要保证在if分支的`res.swap(ptr->data)`之后执行，即需要保证对ptr指针的引用是happens-before关系，因此`ptr->internal_count.fetch_add`的内存顺序是std::memory_order_acquire。至于在原代码中不是acquire，而是std::memory_order_relaxed的原因是`else if`内部的internal_count会使用acquire。