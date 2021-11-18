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

## Avoid inheriting from classes that were not designed to be base classes

Bad eg: Inheriting a class with a public nonvirtual destructor.

## Public inheritance is substitutability. Inheri, not to reuse, whereas to be reused

The "is-a" description of public inheritance is misunderstood when people use it to draw irrelevant real-world analogies: 

A Square "is-a" Rectangle(mathematically) but a Sqaure is not a Rectangle(behaviorally). Therfore you should design Square and Rectangle independently.

Finally, I like following sentence:

> The purpose of public inheritance is not for the derived class to reuse base class code to implement itself in terms of the base class's code. Such an is-implemented-in-terms-of relationship can be entirely proper, but should be modeled by composition--or, in special cases only, by nonpublic inheritance.

## Pimpl judiciously

In short, this item means that you can encapsulate all one class' private variables and private methods into an strcuture. Therefore you can forward-declare the structure within that class and use a pointer pointing to the structure, such as following code snippet:

```c
class Map{
	//...
private:
	struc Impl;
    shared_ptr<Impl> pimpl_;
}
```

This will produce following benefits:

- Shorten compilation time because of forward declaration

- Git rid of ambiguity of name lookup:

  ```c
  int Twice(int); // 1
  
  class Calc {
  public:
  	std::string Twice(std::string); // 2
  private:
  	char* Twice(char*);  // 3
  
  	int Test() {
  		return Twice(21); // error: 2 and 3 are unviable(and 1 is hidden)
  	}
  };
  
  	Calc c;
  	c.Twice("aaa") // error: although 2 is right(implicit conversion from char* to std::string)
  				   // but its' private version(3) is more accurate
  ```

- Make some operations reversible:

  ```c
  class Widget {
  public:
  	Widget& operator=(const Widget&);
  
  private:
  	T1 t1;
  	T2 t2;
  };
  ```

  Say we call the Widget's assignment constructor operator, if the assignment of t1 succeeded, but the assignment of t2 failed and throwed an exception, the whole assignment constructor operator failed and couldn't be reversible.
  
  If we use Pimpl as following:
  
  ```c
  Widget& Widget::operator=(const Widget& widget) {
  	std::shared_ptr<Impl> temp(new Impl(/*...*/));
  	// change temp->t1 and temp->t2; if it fails then throw, else assigns temp
  
  	pimpl_ = temp;
  	return *this;
  }
  
  ```

## Define and initialize member variables in the same order

Member variables are always initialized in the order they are declared in the class definition; the order you write them in the constructor initialization list is ignored:

```c
class Employee {
public:
	std::string m_email;
	std::string m_firstName;
	std::string m_lastName;

	Employee(const char* firstName, const char* lastName) :
		m_firstName(firstName), m_lastName(lastName),
		m_email(m_firstName + "." + m_lastName) { }
};

Employee e("firstName", "lastName");
```

When I test above example, the compilation of it was successful, with no error and warning using VS. But when I ran it, it crashed. The reason is that the m_email member vairable was initialized firstly, using not-yet-initialized member variables(m_firstName and m_lastName).

The reason for this language design decision is to ensure there is a unique order to destroy members.

## Copy and destroy consistently(The Rule of the Big Three)

If you define any of the Big Five(copy constructor, copy assginment operator, move constructor, move assignment operator, destructor), you might need to define one or both of the others:

- If you write/disable either a copy constructor or the copy assignment operator, you probably need to do the same for the other
- If you explicitly write the copying functions, you probably need to write the destructor.
- If you explicitly write the destructor, you probably need to explicitly write or disable copying: If you define a destructor, which means you may need to deallocate some resources, you should define copying constructors. If you don't define them, you should disable them so that your defined classes wouldn't be copied unexpectedly, such as a shallow copy.

> See [The Rule of the BigFive](https://en.cppreference.com/w/cpp/language/rule_of_three) for more details.




















