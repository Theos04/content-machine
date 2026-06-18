# Z shell

**Source**: https://en.wikipedia.org/wiki/Z_shell

The Z shell (Zsh) is a shell and a command-line interpreter for shell scripts. Zsh mostly maintains the Bourne shell's syntax and behavior, but in its default configuration deviates in some significant ways from the POSIX standard specification of the sh language (such as eliminating implicit IFS-splitting and globbing upon unquoted parameter expansions) and adds substantially more features. 
Zsh was created by Paul Falstad in 1990 while he was a student at Princeton University. It combines features from both ksh and tcsh (and rc to a lesser extent), offering functionality such as programmable command-line completion, extended file globbing, improved variable/array handling, and themeable prompts.
Zsh is available for most POSIX / Unix-like operating systems as well as Microsoft Windows as part of Cygwin or the UnxUtils collection and has been adopted as the default interactive shell for macOS, Deepin, TrueNAS and Kali Linux. The "Oh My Zsh" user community website provides a platform for third-party plug-ins and themes, featuring a large and active contributor base.


== History ==
Paul Falstad wrote the first version of Zsh in 1990 while a student at Princeton University. The name Zsh derives from the name of Zhong Shao, a teaching assistant at Princeton University. Falstad regarded Shao's login, "zsh", as a good name for a shell.
Zsh was at first intended to be a subset of csh for the Amiga, but expanded far beyond that. By the time of the release of version 1.0 in 1990 the aim was to be a cross between ksh and tcsh –a powerful "command and programming language" that is well-designed and logical (like ksh), but also built for humans (like tcsh), with all the neat features like spell checking, login/logout watching and termcap support that were "probably too weird to make it into an AT&T product".
Ports of Zsh for Microsoft Windows have been available via Cygwin at least since around 1997, and Zsh is supplied as an official Cygwin package since 2002. It is also available as part of the UnxUtils collection of native Win32 ports of common GNU Unix-like utilities (though Zsh, unlike Bash, is not part of the GNU project itself).
In 2019, macOS Catalina adopted Zsh as the default login shell, replacing the GPLv2 licensed version of Bash, and when Bash is run interactively on Catalina, a warning is shown by default.
The default shell of TrueNAS (formerly FreeNAS) changed from csh to Zsh in FreeNAS 11.2 released in late 2018.
In 2020, Kali Linux adopted Zsh as the default shell since its 2020.4 release.


== Features ==

Features include:

Programmable command-line completion that can help the user type both options and arguments for most used commands, with out-of-the-box support for several hundred commands
Sharing of command history among all running shells
Extended file globbing allows file specification without needing to run an external program such as find
Improved variable/array handling (non-zero-based numbering)
Editing of multi-line commands in a single buffer
Spelling correction and autofill of command names (and optionally arguments, presumably file names)
Various compatibility modes, e.g. Zsh can pretend to be a Bourne shell when run as /bin/sh
Themeable prompts, including the ability to put prompt information on the right side of the screen and have it auto-hide when typing a long command
Loadable modules, providing among other things: full TCP and Unix domain socket controls, an FTP client, and extended math functions.
The built-in where command. Works like the which command but shows all locations of the target command in the directories specified in $PATH rather than only the one that will be used.
Named directories. This allows the user to set up shortcuts such as ~mydir, which then behave the way ~ and ~user do.
Widgets. Both built and implemented by ordinary functions widgets can be bound to hotkeys.
Function autoloading. A performance optimization for function that might be pre-loaded and run on demand. The intent of loading functions as separate file is also to support function features across different Zsh versions.


== Community ==

A user community website known as "Oh My Zsh" collects third-party plug-ins and themes for the Z shell. As of 2024, their GitHub repository has over 2300 contributors, over 300 plug-ins, and over 140 themes. It also comes with an auto-update tool that makes it easier to keep installed plug-ins and themes updated.


== See also ==

Comparison of command shells


== References ==


== External links ==
Z shell on SourceForge
Oh My Zsh

## Related Wikipedia Links

- [Almquist shell](https://en.wikipedia.org/wiki/Almquist_shell)
- [Amiga](https://en.wikipedia.org/wiki/Amiga)
- [Array data structure](https://en.wikipedia.org/wiki/Array_data_structure)
- [Autofill](https://en.wikipedia.org/wiki/Autofill)
- [Bash (Unix shell)](https://en.wikipedia.org/wiki/Bash_(Unix_shell))
- [Bourne shell](https://en.wikipedia.org/wiki/Bourne_shell)
- [C (programming language)](https://en.wikipedia.org/wiki/C_(programming_language))
- [C Shell](https://en.wikipedia.org/wiki/C_Shell)
- [C shell](https://en.wikipedia.org/wiki/C_shell)
- [Command-line completion](https://en.wikipedia.org/wiki/Command-line_completion)
- [Command-line interface](https://en.wikipedia.org/wiki/Command-line_interface)
- [Command history](https://en.wikipedia.org/wiki/Command_history)
- [Comparison of command shells](https://en.wikipedia.org/wiki/Comparison_of_command_shells)
- [Cross-platform](https://en.wikipedia.org/wiki/Cross-platform)
- [Cygwin](https://en.wikipedia.org/wiki/Cygwin)
- [Deepin](https://en.wikipedia.org/wiki/Deepin)
- [File Transfer Protocol](https://en.wikipedia.org/wiki/File_Transfer_Protocol)
- [Find (Unix)](https://en.wikipedia.org/wiki/Find_(Unix))
- [Fish (Unix shell)](https://en.wikipedia.org/wiki/Fish_(Unix_shell))
- [GNU](https://en.wikipedia.org/wiki/GNU)
