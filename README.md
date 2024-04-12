# migrate2gitlfs

Simple and quick migration script to convert a simple linear git repo into
git lfs in a non-destructive way.

Non-destructive means all the action happens on a separate repository, the source
repository is left unchanged.

Read caveats for more info.

Even if you plan to use `git lfs migrate` later, the analysis command might
actually help you analyze the repo.

## Before you start

Install requirements (GitPython):

```sh
$ python3 -m pip install -r requirements.txt
```

## Quick start

First analyze the repository to let the tool find out LFS candidate files,
review the configuration created, and then migrate the repo.

```sh
$ python3 migrate2gitlfs.py analyze --branch main -v local_repo
$ python3 migrate2gitlfs.py migrate --branch main -v local_repo
```

This tool works only with local repos, although if a remote repo is provided
it will download it to a local folder.

```sh
$ python3 migrate2gitlfs.py analyze -v git@github.com:pausan/cblack.git
$ python3 migrate2gitlfs.py migrate -v git@github.com:pausan/cblack.git
```

In this latter case, when cloning cblack repo, the following new files and
folders will be created:

- ./cblack.git
- ./cblack.git-config.json
- ./cblack.git-clone
- ./cblack.git-lfs

Three repositories will be created. Speed and simplicity comes at a cost with
this tool, you'll need at most 3x the space (usually less). The original repo
(which will remain untouched), the cloned repo, on which commits will be
replayed, and the lfs repo, which is the final LFS repo with the rewritten
history.

## Intro

The main use-case is to migrate a repository from another control version tool,
such as subversion or perforce, and then you want to convert it to LFS.

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
history and replacing text in specific files. This script has support for all
that.

## Features & caveats

This tool has some features and caveats you should be aware of.

**Features:**

  - Migrates a single branch
  - Preserves:
    - Commits (all info: authors, dates and messages)
    - Commit tags (authors, dates and messages)
  - Specified patterns are added as LFS
  - Removes specific files from history
  - Analyzes commit history looking for LFS files and secrets files
  - Normal tags are preserved

**Caveats:**

  - History is rewritten
  - All commit hashes change
  - Only one branch will be migrated
  - All commits will be rebased as if all commits happened on one branch
  - Special "tags" such as blobs or trees are lost (unusual to have them, but
    anyway)

## Modes

It contains three modes. `analyze` mode, `migrate` mode and `show` mode.

### analyze

Analysis mode allows to examine the whole repository history looking for all
candidate LFS files (binary files). By default this tool has a pre-defined list
of most common LFS files, but still, it is probable that your project will
contain other files.

This mode will also find candidate files to be deleted and/or will warn you
about other stuff.

After you run this mode, **you should proceed to review and edit the json file**
in order to set your preferences and adjust the parameters for the migration.

Sample:

```json
{
  "authors": {
    "Pau <contact@pausanchez.com>": {
      "name": "Pau Sanchez",
      "email": "contact@pausanchez.com"
    },
  },
  "warnings": [
    "File can contain sensitive info: path/to/secret.cer",
  ],
  "history_rename_files": {
    "search_string" : "replacement_string"
  },
  "history_delete_files": [
    "path/file/to/be/removed.json"
  ],
  "history_replace_file_contents": {
    "path/to/secrets.json": {
      "search_string": "replacement_string"
    }
  },
  "lfs_patterns": ["default", "*.pyo"],
  "extra_lfs_patterns": [
    "path/to/large-binary-file",
    "*.bin"
  ]
}
```

- **authors**: This the mapping of name and email as it appears on git history
  in the original/cloned repo, and the name/email you want to use in the new
  rewritten lfs repo

- **warnings**: List of warnings or things you should be aware of when
  converting this project into lfs. The warnings are in textual form. This tool
  might detect secret files that you might want to delete, but it is up to you
  to act on these warnings.

- **history_rename_files**: Dictionary containing pairs of *search* and
  *replacement* strings that will be applied to file names. This way you can
  rename full paths, all file names or just static patterns when replaying
  history. In the dict you can put several search/replacement pairs, but all
  will be applied to all files in the history, so be careful.

- **history_delete_files**: List of paths/files that you'd like to be deleted
  from history. Please note that only specified paths will be deleted. If a file
  was added as path/to/file1.cer and later moved to path/to/secret.cer and you
  specified the latter, only the latter will be deleted, thus, you should add
  all files. This field does not allow patterns, just full paths.

  This field is NOT updated by analysis command.

- **history_replace_file_contents**: List of files containing a dict of
  search/replace pairs. The script will iterate through history doing a search
  and replace inplace inside the file for specific search/replace patterns.
  Files will be opened in binary mode, read in memory and written back to disk.

- **lfs_patterns**: here `default` and `none` are special keywords. This tool
  contains a big list of default binary files that you might want to use, so
  feel free to leave it as is (using default). Otherwise you can specify a list
  of comma-separated patterns or extensions like ("png, jpeg, path/to/file*,
  gif"), or just provide a extra json array with the patterns you'd like.

  This field is NOT updated by analysis command (but its contents are used to
  generate extra_lfs_patterns, everything not matching lfs_patterns will be
  included in extra_lfs_patterns).

- **extra_lfs_patterns**: here you should add a list of patterns or file names
  that you'd like to be part of LFS. This is separated from `lfs_patterns` so
  that default list can be easily reused.

Please note that if you only want to search and replace in history or delete
files, while this tool can do the job if you disable LFS, all commits will be
rewritten, and this tool does not handle branches. You might want to use git
itself.

### show

- **gitattributes**: use this parameter to show the final .gitattributes file
  that will be used for the project.

- **deleted**: use this parameter to show all the files that are going to
  be removed throught the whole history. It will show the first commit
  in which such files appear and a guess on the minimum space to be freed (this
  is just orientative).

Example:

```sh
$ python3 migrate2gitlfs.py show gitattributes -v local_repo
$ python3 migrate2gitlfs.py show deleted -v local_repo
```

### migrate

Migrate mode performs the actual migration, based on the configuration files
created in the analysis phase

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
