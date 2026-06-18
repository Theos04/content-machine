# Shell script

**Source**: https://en.wikipedia.org/wiki/Shell_script

A shell script is a computer program designed to be run by a Unix shell, a command-line interpreter. The various dialects of shell scripts are considered to be command languages. Typical operations performed by shell scripts include file manipulation, program execution, and printing text. A script which sets up the environment, runs the program, and does any necessary cleanup or logging, is called a wrapper.
The term is also used more generally to mean the automated mode of running an operating system shell. Different operating systems each use a particular name for these functions.  All Unix-like systems include at least one POSIX shell, typically either bash or the zsh compatibility mode..


== Capabilities ==


=== Comments ===
Comments are ignored by the shell. They typically begin with the hash symbol (#), and continue until the end of the line.


=== Configurable choice of scripting language ===
The shebang, or hash-bang, is a special kind of comment which the system uses to determine what interpreter to use to execute the file. The shebang must be the first line of the file, and start with "#!". In Unix-like operating systems, the characters following the "#!" prefix are interpreted as a path to an executable program that will interpret the script.


=== Shortcuts ===
A shell script can provide a convenient variation of a system command where special environment settings, command options, or post-processing apply automatically, but in a way that allows the new script to still act as a fully normal Unix command.
One example would be to create a version of ls, the command to list files, giving it a shorter command name of l, which would be normally saved in a user's bin directory as /home/username/bin/l, and a default set of command options pre-supplied.

Here, the first line uses a shebang to indicate which interpreter should execute the rest of the script, and the second line makes a listing with options for file format indicators, columns, all files (none omitted), and a size in blocks. The LC_COLLATE=C sets the default collation order to not fold upper and lower case together, not intermix dotfiles with normal filenames as a side effect of ignoring punctuation in the names (dotfiles are usually only shown if an option like -a is used), and the "$@" causes any parameters given to l to pass through as parameters to ls, so that all of the normal options and other syntax known to ls can still be used.
The user could then simply use l for the most commonly used short listing.
Another example of a shell script that could be used as a shortcut would be to print a list of all the files and directories within a given directory.

In this case, the shell script would start with its normal starting line of #!/bin/sh. Following this, the script executes the command clear which clears the terminal of all text before going to the next line. The following line provides the main function of the script. The ls -al command lists the files and directories that are in the directory from which the script is being run. The ls command attributes could be changed to reflect the needs of the user.


=== Batch jobs ===
Shell scripts allow several commands that would be entered manually at a command-line interface to be executed automatically, and without having to wait for a user to trigger each stage of the sequence. For example, in a directory with three C source code files, rather than manually running the four commands required to build the final program from them, one could instead create a script for POSIX-compliant shells, here named build and kept in the directory with them, which would compile them automatically:

The script would allow a user to save the file being edited, pause the editor, and then just run ./build to create the updated program, test it, and then return to the editor. Since the 1980s or so, however, scripts of this type have been replaced with utilities like make which are specialized for building programs.


=== Generalization ===
Simple batch jobs are not unusual for isolated tasks, but using shell loops, tests, and variables provides much more flexibility to users. A POSIX sh script to convert JPEG images to PNG images, where the image names are provided on the command-line—possibly via wildcards—instead of each being listed within the script, can be created with this file, typically saved in a file like /home/username/bin/jpg2png

The jpg2png command can then be run on an entire directory full of JPEG images with just /home/username/bin/jpg2png *.jpg


=== Programming ===
Many modern shells also supply various features usually found only in more sophisticated general-purpose programming languages, such as control-flow constructs, variables, comments, arrays, subroutines and so on. With these sorts of features available, it is possible to write reasonably sophisticated applications as shell scripts. However, they are still limited by the fact that most shell languages have little or no support for data typing systems, classes, threading, complex math, and other common full language features, and are also generally much slower than compiled code or interpreted languages written with speed as a performance goal.
The standard Unix tools sed and awk provide extra capabilities for shell programming; Perl can also be embedded in shell scripts as can other scripting languages like Tcl. Perl and Tcl come with graphics toolkits as well.


== Typical shell languages ==

Scripting languages commonly found on UNIX, Linux, and POSIX-compliant operating system installations include:

The original Bourne shell (sh), though no longer in common use
GNU Bash (bash)
Debian Almquist shell (dash)
Z shell (zsh) if run in compatibility mode
Non-POSIX shells in common use include:

Nushell (nu)
Fish shell (fish)
xonsh shell (xonsh), pronounced "conch", a Python-based shell
PowerShell (pwsh)
The C and Tcl shells have syntax quite similar to that of similarly-named programming languages, and the Korn shells and Bash are developments of the Bourne shell, which is based on the ALGOL language with elements of a number of others added as well. On the other hand, the various shells plus tools like awk, sed, grep, and BASIC, Lisp, C and so forth contributed to the Perl programming language.
Formerly-popular shells include:

Old shell (osh), a "port of the standard command interpreter from Sixth Edition UNIX"
KornShell (ksh), since mostly replaced by its successor the Z shell
Tenex C Shell (tcsh) and its predecessor the C shell (csh)
Related programs such as shells based on Python, Ruby, C, Java, Perl, Pascal, Rexx etc. in various forms are also widely available.
So called remote shells such as 

a Remote Shell (rsh)
a Secure Shell (ssh)
are really just tools to run a more complex shell on a remote system and have no 'shell' like characteristics themselves.


== Other scripting languages ==

Many powerful scripting languages, such as Rexx, Python, Perl, and Tcl, have been introduced to address tasks that are too large, complex, or repetitive to be comfortably handled by traditional shell scripts, while avoiding the overhead associated with compiled languages like C or Java.
Although the distinction between scripting languages and general-purpose high-level programming languages is often debated, scripting languages are typically characterized by their interpreted nature, simplified syntax, and primary use in automating tasks, coordinating system operations, and writing "glue code" between components. Even when scripting languages such as Python, Rexx, or JavaScript support compilation to bytecode or use JIT to improve performance, they are still commonly referred to as "scripting languages" due to their historical association with automation, lightweight tooling, and scripting environments rather than standalone application development.
Scripting is a form of programming. While "scripting" may emphasize lightweight, task-oriented automation, the broader term "programming" encompasses both scripting and software development in compiled or structured languages. As such, scripting involves writing code to instruct a computer to perform specific tasks—meeting the fundamental definition of programming.


== Life cycle ==
Shell scripts often serve as an initial stage in software development, and are often subject to conversion later to a different underlying implementation, most commonly being converted to Perl, Python, or C. The interpreter directive allows the implementation detail to be fully hidden inside the script, rather than being exposed as a filename extension, and provides for seamless reimplementation in different languages with no impact on end users.
While files with the ".sh" file extension are usually a shell script of some kind, most shell scripts do not have any filename extension.


== Advantages and disadvantages ==
One of the biggest advantages of writing a shell script is that the commands and syntax are exactly the same as those directly entered at the command-line. The programmer does not have to switch to a totally different syntax, as they would if the script were written in a different language, or if a compiled language were used.
Often, writing a shell script is much quicker than writing the equivalent code in other programming languages. The many advantages include easy program or file selection, quick start, and interactive debugging. A shell script can be used to provide a sequencing and decision-making linkage around existing programs, and for moderately sized scripts the absence of a compilation step is an advantage. Interpretive running makes it easy to write debugging code into a script and re-run it to detect and fix bugs. Non-expert users can use scripting to tailor the behavior of programs, and shell scripting provides some limited scope for multiprocessing.
On the other hand, shell scripting is prone to costly errors. Inadvertent typing errors such as rm -rf * / (instead of the intended rm -rf */) are folklore in the Unix community; a single extra space converts the command from one that deletes all subdirectories contained in the current directory, to one which deletes everything from the file system's root directory. Similar problems can transform cp and mv into dangerous weapons, and misuse of the > redirect can delete the contents of a file.
Another significant disadvantage is the slow execution speed and the need to launch a new process for almost every shell command executed. When a script's job can be accomplished by setting up a pipeline in which efficient filter commands perform most of the work, the slowdown is mitigated, but a complex script is typically several orders of magnitude slower than a conventional compiled program that performs an equivalent task.
There are also compatibility problems between different platforms. Larry Wall, creator of Perl, famously wrote that "It's easier to port a shell than a shell script."
Similarly, more complex scripts can run into the limitations of the shell scripting language itself; the limits make it difficult to write quality code, and extensions by various shells to ameliorate problems with the original shell language can make problems worse.
Many disadvantages of using some script languages are caused by design flaws within the language syntax or implementation, and are not necessarily imposed by the use of a text-based command-line; there are a number of shells which use other shell programming languages or even full-fledged languages like Scsh (which uses Scheme).


== Interoperability among scripting languages ==
Many scripting languages share similar syntax and features due to their adherence to the POSIX standard, and several shells provide modes to emulate or maintain compatibility with others. This allows scripts written for one shell to often run in another with minimal changes.
For example, Bash supports much of the original Bourne shell syntax and offers a POSIX-compliant mode to improve portability. However, Bash also includes a number of extensions not found in POSIX, commonly referred to as bashisms. While these features enhance scripting capabilities, they may reduce compatibility with other shells like Dash or ksh.


== Shell scripting on other operating systems ==
Interoperability software such as Cygwin, the MKS Toolkit, Interix (formerly part of Microsoft Windows Services for UNIX), Hamilton C shell, and UWIN (AT&T Unix for Windows) enables Unix shell programs to run on Windows NT-based systems, though some features may not be fully supported on the older MS-DOS/Windows 95 platforms. Earlier versions of the MKS Toolkit also provided support for OS/2. 
Scripting languages are, by definition, able to be extended. On Unix and other POSIX-compliant systems, awk and sed are used to extend the string and numeric processing ability of shell scripts. Tcl, Perl, Rexx, and Python have graphics toolkits and can be used to code functions and procedures for shell scripts which pose a speed bottleneck (C, Fortran, assembly language &c are much faster still) and to add functionality not available in the shell language such as sockets and other connectivity functions, heavy-duty text processing, working with numbers if the calling script does not have those abilities, self-writing and self-modifying code, techniques like recursion, direct memory access, various types of sorting and more, which are difficult or impossible in the main script, and so on. Visual Basic for Applications and VBScript can be used to control and communicate with such things as spreadsheets, databases, scriptable programs of all types, telecommunications software, development tools, graphics tools and other software which can be accessed through the Component Object Model.


== See also ==
Glue code
Interpreter directive
Shebang symbol (#!)
Unix shells
PowerShell
Windows Script Host


== References ==


== External links ==

An Introduction To Shell Programming by Greg Goebel
UNIX / Linux shell scripting tutorial by Steve Parker
Shell Scripting Primer (Apple)
What to watch out for when writing portable shell scripts by Peter Seebach
Free Unix Shell scripting books
Beginners/BashScripting, Ubuntu Linux

## Related Wikipedia Links

- [ALGOL](https://en.wikipedia.org/wiki/ALGOL)
- [APL (programming language)](https://en.wikipedia.org/wiki/APL_(programming_language))
- [Ada (programming language)](https://en.wikipedia.org/wiki/Ada_(programming_language))
- [Assembly language](https://en.wikipedia.org/wiki/Assembly_language)
- [Awk](https://en.wikipedia.org/wiki/Awk)
- [BASIC](https://en.wikipedia.org/wiki/BASIC)
- [Bash (Unix shell)](https://en.wikipedia.org/wiki/Bash_(Unix_shell))
- [Bourne shell](https://en.wikipedia.org/wiki/Bourne_shell)
- [Brian Kernighan](https://en.wikipedia.org/wiki/Brian_Kernighan)
- [C++](https://en.wikipedia.org/wiki/C++)
- [COBOL](https://en.wikipedia.org/wiki/COBOL)
- [C (programming language)](https://en.wikipedia.org/wiki/C_(programming_language))
- [C Sharp (programming language)](https://en.wikipedia.org/wiki/C_Sharp_(programming_language))
- [C shell](https://en.wikipedia.org/wiki/C_shell)
- [Caml](https://en.wikipedia.org/wiki/Caml)
- [Command-line interpreter](https://en.wikipedia.org/wiki/Command-line_interpreter)
- [Command language](https://en.wikipedia.org/wiki/Command_language)
- [Comment (computer programming)](https://en.wikipedia.org/wiki/Comment_(computer_programming))
- [Comparison of programming languages](https://en.wikipedia.org/wiki/Comparison_of_programming_languages)
- [Component Object Model](https://en.wikipedia.org/wiki/Component_Object_Model)
