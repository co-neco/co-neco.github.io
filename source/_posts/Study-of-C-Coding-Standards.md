---
title: Study of C++ Coding Standards
categories:
  - Technology
  - Development
date: 2021-11-03 20:32:18
tags:
  - C++
  - Coding Standards
---

In this article, I would write my own comprehension of the book, C++ Coding Standards, for following aims:
- Continuous study about design pattern, refactoring
- Give me some hints about software development when coming across difficulties
- Review what I wrote for Reminding what I should take care of

# Project organization

## Use an automated build system
When you develop a large project, you should always do following two things:
- Write a corresponding configuration project to automatically configure what you would configure manually otherwise.
    > As time goes by, you may need add some configurations, such as an addition of a new task. You may do so by adding following sentences:
    >
    > ```c
    > // Configuration file A
    > auto taskB = new TaskB(some parameters);
    > sm_allTasks.push_back(taskB);
    > 
    > // Configuration file B
    > {
    >     "taskA":{
    >         "attribute1": 123,
    >         "attribute2": 456
    >     },
    >     "taskB":{
    >         "attribute1": 789,
    >         "attribute2": 111
    >     }
    > }
    > ```
    >
    > If we write a  corresponding configuration project, we could just run it without any manual operations. Besides, there may be many places need to be modified when adding a new task, which is error-prone. Whereas, the configuration project can take all situations into account.

- Use an automated build system

    > Like the first tip, as projects grow over time, so does the cost of not having an automated build. Therefore, You should not do whatever configuration projects can do for you.

# Design style

## Correctness, simplicity, and clarity come first

In this Item, I like what Steve McConnell said:

> Write programs for people first, computers second. --Steve McConnell

## Don't optimize prematurely

Always remember:

> It it far, far easier to make a correct program fast than it is to make a fast program correct.
>
> When developing a large project, we should first guarantee projects' readability and clarity. We should include optimizations later when all things are in place--and only if necessary.

## Be careful when using RAII

Perform every explicit resource allocation(e.g., new) in its own statement that immediately gives the allocated resource to a manager object(e.g., shared_ptr).

If you define a function and use it like following example:

```c
void Func(shared_ptr<Widget> sp1, shared_ptr<Widget> sp2);
//...
Func(shared_ptr<Widget>(new Widget), shared_ptr<Widget>(new Widget));
```

Such usage is unsafe. Some compiler may allocate two widgets at first, and then call their constructors sequentially. If the first constructor throws an exception, the second allocated widget can not be caught by shared_ptr, and thus cause a memory leak.

There is a workaround for it:

```c
shared_ptr<Widget> sp1(new Widget), sp2(new Widget);
Func(sp1, sp2);
```

There is one another example that I picked up from PVS SAST tool [blog](https://pvs-studio.com/en/blog/posts/cpp/0873/):

```c
std::vector<std::unique_ptr<Modifier>> Modifiers;
Modifiers.emplace_back(new LoadModifier(BB, &PT, &R));
Modifiers.emplace_back(new StoreModifier(BB, &PT, &R));
```

As you know, vector is a template. If you pass a class instance address allocated by 'new' like above second line, std::unique_ptr will manage that class instance after emplace_back is called.

What if emplace_back throws an exception?  oops!!! That class instance would hang forever.

There is a workaround  for it:

```c
std::vector<std::unique_ptr<Modifier>> Modifiers;
Modifiers.emplace_back( std::unique_ptr<LoadModifier>(new LoadModifier(BB, &PT, &R)));
```

So the best practice is that never allocate more than one resource in a single statement, and perform every explicit resource allocation in its own code statement that **immediately** gives the resource to an owning object(e.g., shared_ptr).

# Coding style

## Minimize definitional dependencies

Last year, I began to develop a large project(I thought ^_^). I met a cyclic dependencies, which two compilation units depend each other. After some search, I found a term called 'forward declarations'. 'Forward declarations' means to just declare a class, whereas not to use '#include' to include a class' full definition. In this way, we can avoid cyclic dependencies.

There is one another example: Visitor design pattern, which has a cyclic dependencise problem. If you want to use visitor design pattern, you can it's workaround design pattern named [acyclic visitor pattern](https://condor.depaul.edu/dmumaugh/OOT/Design-Principles/acv.pdf).

# Functions and Operations

## Prefer the canonical forms of arithmetic and assignment operators

If you define 'a +b' operator, you should always define 'a += b' operator:

```c
T& T::operator@=(const T&){
//... implementation
return *this;
}

T operator@(const T& lhs, const T& rhs){
	T temp(lhs);
	return temp @= rhs;
}
```

Note that here operator@ is a nonmember function, so that it can accept the same implicit conversions on its left-hand side and right-hand side parameters, like following code snippet:

```c
'Char + String' and 'String + Char' are both OK.
```

In any case, put all nonmember operators in the same namespace as T so that they will be conveniently available to callers as well as to avoid name lookup surprises.

## Perfer calling the prefix forms of ++ or --

If you do not need the original value, use the prefix version, which would not create a temporary object.

## Consider overloading to avoid implicit type conversions

Consider that if you made a string comparison, such as the following example:

```c
if (someString == "Hello") {...}
```

If you just defined following operator==

```c
class String{
bool operator==(const String&, const String&);
}
```

There is a implicit type conversion from char* to String, which need a copy of "Hello". As you can see, it would waste cpu and memory resources.

There is a workaround:

```c
bool operator==(const String&, const String&);
bool operator==(const String&, const char*);
bool operator==(const char*, const String&);
```

That seems like a lot of code duplication, but actually it's just only "signature duplication" because all three typically use the same back-end function.

Try the rule if you make a library that must meets some performance need. 

## Don't write code that depends on the order of evaluation of function arguments.

Consider following situation:

```c
void Func(int, int);

int count = 5;
Func(++count, ++count);
```

When the Func is called, you know 'count' variable equals to 7, but you don't know which of the two parameters is 6 and which is 7.

# Class Design and Inheritance

## Be clear what kind of class you're writing

This is the first rule of current section, and I think it's indeed the valuest and best rule.

In short, Know which kind class you are writing. You can get a more detailed description of the rule from the [book](http://library.bagrintsev.me/CPP/Sutter.C%2B%2B%20Coding%20Standards.2005.pdf).

## Prefer composition to inheritance

If you learned design pattern, you should know what is composition.

To avoid tight coupling and class explosion, you should use composition except inheritance is necessary.







