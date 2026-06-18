# NOP (code)

**Source**: https://en.wikipedia.org/wiki/NOP_(code)

In computer science, a NOP, no-op, or NOOP (pronounced "no op"; short for no operation) is a machine language instruction and its assembly language mnemonic, programming language statement, or computer protocol command that does nothing.


== Machine language instructions ==
Some computer instruction sets include an instruction whose purpose is to not change the state of any of the programmer-accessible registers, status flags, or memory. It often takes a well-defined number of clock cycles to execute. In other instruction sets, there is no explicit NOP instruction, but the assembly language mnemonic NOP represents an instruction which acts as a NOP; e.g., on the SPARC, sethi 0, %g0.
A NOP must not access memory, as that could cause a memory fault or page fault. 
A NOP is most commonly used for timing purposes, to force memory alignment, to prevent hazards, to occupy a branch delay slot, to render void an existing instruction such as a jump, as a target of an execute instruction, or as a place-holder to be replaced by active instructions later on in program development (or to replace removed instructions when reorganizing would be problematic or time-consuming). In some cases, a NOP can have minor side effects; for example, on the Motorola 68000 series of processors, the NOP opcode causes a synchronization of the pipeline.
Listed below are the NOP instruction for some CPU architectures:

From a hardware design point of view, unmapped areas of a bus are often designed to return zeroes; since the NOP slide behavior is often desirable, it gives a bias to coding it with the all-zeroes opcode.


== Code ==
A function or a sequence of programming language statements is a NOP or null statement if it has no effect. Null statements may be required by the syntax of some languages in certain contexts.


=== Ada ===
In Ada, the null statement serves as a NOP. As the syntax forbids that control statements or functions be empty, the null statement must be used to specify that no action is required. (Thus, if the programmer forgets to write a sequence of statements, the program will fail to compile.)


=== C and derivatives ===
The simplest NOP statement in C is the null statement, which is just a semi-colon in a context requiring a statement.
Most C compilers generate no code for null statements, which has historical and performance reasons. 

  ;

An empty block (compound statement) is also a NOP, and may be more legible, but will still have no code generated for it by the compiler.

  {}

In some cases, such as the body of a function, a block must be used, but this can be empty. In C, statements cannot be empty—simple statements must end with a ; (semicolon) while compound statements are enclosed in {} (braces), which does not itself need a following semicolon. Thus in contexts where a statement is grammatically required, some such null statement can be used.
The null statement is useless by itself, but it can have a syntactic use in a wider context, e.g., within the context of a loop:

alternatively,

or more tersely:

The last form might generate a warning with some compilers or compiler options, as a semicolon placed after a parenthesis at the end of a line usually indicates the end of a function call expression.
The above code continues calling the function getchar() until it returns a \n (newline) character, essentially fast-forwarding the current reading location of standard input to the beginning of next line.


=== Fortran ===
In Fortran, the CONTINUE statement is used in some contexts such as the last statement in a DO loop, although it can be used anywhere, and does not have any functionality.


=== JavaScript ===
The JavaScript language does not have a built-in NOP statement. Many implementations are possible:

Use the ; empty statement or the {} empty block statement the same way as in the C and derivatives examples;
Use the undefined or the null expression as a complete statement (an expression statement) when the previous methods are not allowed by the syntax.
Alternatives, in situations where a function is required, are:

Use the Function.prototype() built-in function, that accepts any arguments and returns undefined;
Use a NOP function available in a third-party library —see below;
Define a custom NOP function, as in the following example (using the ES6 arrow function syntax):


==== AngularJS ====
The AngularJS framework provides angular.noop function that performs no operations.


==== jQuery ====
The jQuery library provides a function jQuery.noop(), which does nothing.


==== Lodash ====
The Lodash library provides a function _.noop(), which returns undefined and does nothing.


=== Pascal ===
As with C, the ; used by itself can be used as a null statement in Pascal. In fact, due to the specification of the language, in a BEGIN / END block, the semicolon is optional before the END statement, thus a semicolon used there is superfluous. 
Also, a block consisting of  BEGIN END; may be used as a placeholder to indicate no action, even if placed inside another BEGIN / END block.


=== Python ===
The Python programming language has a pass statement which has no effect when executed and thus serves as a NOP. It is primarily used to ensure correct syntax due to Python's indentation-sensitive syntax; for example the syntax for definition of a class requires an indented block with the class logic, which has to be expressed as pass when it should be empty.


=== Shell scripting (bash, zsh, etc.) ===
The ':' [colon] command is a shell builtin that has similar effect to a "NOP" (a do-nothing operation). It is not technically an NOP, as it changes the special parameter $? (exit status of last command) to 0. It may be considered a synonym for the shell builtin 'true', and its exit status is true (0).


=== TeX macro language (ConTeXt, LaTeX, etc.) ===
The TeX typographical system's macro language has the \relax command. It does nothing by itself, but may be used to prevent the immediately preceding command from parsing any subsequent tokens.


== NOP protocol commands ==
Many computer protocols, such as telnet, include a NOP command that a client can issue to request a response from the server without requesting any other actions. Such a command can be used to ensure the connection is still alive or that the server is responsive. A NOOP command is part of the following protocols (this is a partial list):

telnet
FTP
SMTP
X11
POP3
NNTP
finger
IMAP4
BitTorrent
Unlike the other protocols listed, the IMAP4 NOOP command has a specific purpose—it allows the server to send any pending notifications to the client.
While most telnet or FTP servers respond to a NOOP command with "OK" or "+OK", some programmers have added quirky responses to the client. For example, the ftpd daemon of MINIX responds to NOOP with the message:

200 NOOP to you too!


== Cracking ==
NOPs are often involved when cracking software that checks for serial numbers, specific hardware or software requirements, presence or absence of hardware dongles, etc. in the form of a NOP slide. This process is accomplished by altering functions and subroutines to bypass security checks and instead simply return the expected value being checked for. Because most of the instructions in the security check routine will be unused, these would be replaced with NOPs, thus removing the software's security functionality without altering the positioning of everything which follows in the binary.


== Security exploits ==
The NOP opcode can be used to form a NOP slide, which allows code to execute when the exact value of the instruction pointer is indeterminate (e.g., when a buffer overflow causes a function's return address on the stack to be overwritten).


== See also ==
Comment (computer programming) – annotations generally for programmers that are ignored by compilers and interpreters
Computer architecture
Filler text
Halt and Catch Fire – also pauses the CPU
HLT (x86 instruction) – pauses the CPU
Identity function – the functional programming equivalent to NOP
IEFBR14 – mainframe tautology
xyzzy (computing) – a command sometimes used instead of NOP
X86 instruction listings#Added in P5/P6-class processors – NOPL, the official long NOP


== References ==

## Related Wikipedia Links

- [6502](https://en.wikipedia.org/wiki/6502)
- [8051](https://en.wikipedia.org/wiki/8051)
- [AMD 29k](https://en.wikipedia.org/wiki/AMD_29k)
- [ARM 11](https://en.wikipedia.org/wiki/ARM_11)
- [ARM architecture family](https://en.wikipedia.org/wiki/ARM_architecture_family)
- [AVR microcontrollers](https://en.wikipedia.org/wiki/AVR_microcontrollers)
- [Acorn Archimedes](https://en.wikipedia.org/wiki/Acorn_Archimedes)
- [Ada (programming language)](https://en.wikipedia.org/wiki/Ada_(programming_language))
- [Addressing mode](https://en.wikipedia.org/wiki/Addressing_mode)
- [AngularJS](https://en.wikipedia.org/wiki/AngularJS)
- [Assembly language](https://en.wikipedia.org/wiki/Assembly_language)
- [BitTorrent (protocol)](https://en.wikipedia.org/wiki/BitTorrent_(protocol))
- [Bit manipulation instructions](https://en.wikipedia.org/wiki/Bit_manipulation_instructions)
- [Branch (computer science)](https://en.wikipedia.org/wiki/Branch_(computer_science))
- [Branch delay slot](https://en.wikipedia.org/wiki/Branch_delay_slot)
- [Byte](https://en.wikipedia.org/wiki/Byte)
- [COP400](https://en.wikipedia.org/wiki/COP400)
- [COP8](https://en.wikipedia.org/wiki/COP8)
- [Central processing unit](https://en.wikipedia.org/wiki/Central_processing_unit)
- [Class (programming)](https://en.wikipedia.org/wiki/Class_(programming))
