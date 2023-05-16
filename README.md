# migrate2gitlfs

Simple and quick migration script to convert a git repo into git lfs.

## Quick start

First analyze the repository to let the tool find out LFS candidate files,
review the configuration created, and then migrate the repo.

```sh
$ python analyze 
```


## Intro

The main use-case is when you are trying to migrate a repository from another
control version tool, such as subversion or perforce, and then you want to
convert it to LFS.

### Why?

As of this writing, `git lfs migrate import` is slow as hell. BFG Repo-Cleaner
tool is not working well anymore to migrate to LFS. Thus, after having to
migrate multiple projects, I just got desperated and tried a more pragmatic
approach.

### How?

Existing tools work with a single repo and play with interanl git objects and
structures in order to do their magic. I don't know enough of git internals to
do it like that, so I just though: How fast would it be if a script cloned a
repo and replayed all history somewhere else, commmit by commit, preserving
messages, authors, dates etc... but with LFS enabled. It also replays tags.

It only works with one branch though.

Since it replays the whole commit history, commit by commit, it is very easy to
change history as well. Things such as renaming authors, deleting files from
history and replacing text in specified files.

## Features & caveats

This tool has some features and caveats you should be aware of.

**Features:**

  - Migrates master/main branch
  - Preserves:
    - Commits (all info: authors, dates and messages)
    - Commit tags (authors, dates and messages)
  - Specified patterns are added as LFS
  - Removes specific files from history
  - Analyzes commit history looking for LFS files and secrets files

**Caveats:**

  - History is rewritten (commit hashes change)
  - Only projects with one branch can be migrated
  - Special tags to blogs or trees (unusual) are lost

## Modes

It contains two modes. `analyze` mode and `migrate` mode

### analyze

Analysis mode allows to examine the whole repository history looking for all
candidate LFS files (binary files). By default this tool has a pre-defined list
of most common LFS files, but still, it is probable that your project will
contain other files.

This mode will also find candidate files to be deleted and/or will warn you
about other stuff.

### migrate



## License

Copyright 2023 Pau Sanchez

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the “Software”), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
