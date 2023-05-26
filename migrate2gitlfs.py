#!/usr/bin/env python
# Copyright 2023 Pau Sanchez
# MIT LICENSE - read LICENSE file

#
# We start with an "original" git repo, that we don't want to touch.
#
# The original repo is used to create a clone that will be used as the source
# repository to replay commits.
#
# The concept is simple, we replay src commits on the clone folder copying
# files to the "target" folder and performing commits there.
#
# The only catch is that we initialize "target" repo as LFS from the beginning
# and we add .gitattributes in the first commit so that everything is managed
# as an LFS file system from that point on.
#
# This code assumes git LFS has already been installed for the current user
# (otherwise just run "git lfs install")
#
import os
import sys
import shutil
import subprocess
import git
import argparse
import json
import fnmatch
import time
import collections
from datetime import datetime

KW_NONE = 'none'
KW_DEFAULT = 'default'

# Compiled non-exhaustive list of typical binary files
# if has '*' that pattern will be treated as is, otherwise like na extension
GITATTRIBUTES_DEFAULT_LFS_PATTERNS = """
# Archives
zip, 7z, gz, rar, tar

# Audio
mp3, m4a, ogg, wav, aiff, aif, mod, it, s3m, xm

# Image
jpg, jpeg, png, apng, atsc, gif, bmp, ico, exr, tga, tiff, tif, iff, pict, dds, xcf, leo, kra, kpp, clip, webm, webp, svg, svgz, psd, afphoto, afdesign, qoi
ai, psd, dwg

# 3D
fbx, obj, max, blend, blender, dae, mb, ma, 3ds, dfx, c4d, lwo, lwo2, abc, 3dm, bin, glb

# Docs
pdf, doc, docx, ppt, pptx, rtf, odt, xls, xlsx

# Fonts
ttc, ttf, otf, font, woff

# Video
mov, avi, asf, mpg, mpeg, mp4, flv, ogv, wmv

# Executables
slo, lo, o, obj, gch, pch, so, dylib, dll, lai, la, a, lib, exe, out, app, pdb, idb
class, jar, war, ear, keystore, dex, apk
dmg

# Other binaries
bin, dat, pak, pack, nib, pyc, pyo, db

# Unity
cubemap
unitypackage
*-[Tt]errain.asset
*-[Nn]av[Mm]esh.asset
"""

LFS_KNOWN_TEXT_EXTENSIONS = set([
  "txt", "md", "csv", "json", "html", "css", "js"
])

def isKnownTextExtension(ext):
  for x in LFS_KNOWN_TEXT_EXTENSIONS:
    if ext.lower().endswith("." + x):
      return True
  return False

def getPatternsFromPatternMultiline(patternsString):
  """ Parse all lines patternsString where each line can either start with a
  comment '#' or be a list of comma-separated file extensions or patterns

  It puts each pattern/extension in a new line and adds the LFS attributes
  """
  patterns = []
  for line in patternsString.strip().split('\n'):
    line = line.strip()
    if not line or line.startswith('#'):
      continue

    extensions = [e.strip() for e in line.split(',')]
    for ext in extensions:
      if not ext: continue

      # looks like an extension (eg, not a path, not a pattern)
      if ('*' not in ext) and ('/' not in ext):
        ext = f'*.{ext}'

      patterns.append(ext)

  return patterns

def gitAttributesLfsFromPatterns(patternsString):
  """ Parse all lines patternsString where each line can either start with a
  comment '#' or be a list of comma-separated file extensions or patterns

  It puts each pattern/extension in a new line and adds the LFS attributes
  """
  if isinstance(patternsString, (list, set, tuple)):
    patternList = list(patternsString)
    try:
      defaultOffset = patternList.index(KW_DEFAULT)
      patternList[defaultOffset] = GITATTRIBUTES_DEFAULT_LFS_PATTERNS
      patternList.insert(defaultOffset+1, "\n# Custom patterns ")
    except:
      pass # default not found!

    return gitAttributesLfsFromPatterns('\n'.join(patternList))

  # treat special keywords
  if patternsString == KW_NONE:
    return ''

  elif patternsString == KW_DEFAULT:
    return gitAttributesLfsFromPatterns(GITATTRIBUTES_DEFAULT_LFS_PATTERNS)

  gitattributes_list = []
  for line in patternsString.strip().split('\n'):
    line = line.strip()
    if not line or line.startswith('#'):
      gitattributes_list.append(line)
      continue

    extensions = [e.strip() for e in line.split(',')]
    for ext in extensions:
      if not ext: continue

      # looks like an extension (eg, not a path, not a pattern)
      if ('*' not in ext) and ('/' not in ext):
        ext = f'*.{ext}'

      gitattributes_list.append(
        f"""{ext:8s} filter=lfs diff=lfs merge=lfs {
          "text" if isKnownTextExtension(ext) else "binary"
        }"""
      )

  return '\n'.join(gitattributes_list)

def gitAttributesMergeDumb(contents1, contents2, separator = ''):
  """ Merge contents2 into contents1 by iterating over each line of
  contents2, and appending to contents1 if it does not exist.

  It is really dumb operation, that might be prone to errors, but hey.
  """
  new_lines = []
  for line in contents2.split('\n'):
    if line in contents1: continue

    new_lines.append (line)

  if not new_lines:
    return contents1

  new_lines = sorted(new_lines)
  return contents1 + f'\n{separator}\n' + '\n'.join(new_lines) + '\n'

def checkRequirements(origin_repo_path, branch_name):
  """ Ensure our requirements are met (e.g only one branch, linear history)
  """
  origin_repo = git.Repo(origin_repo_path)

  if branch_name not in origin_repo.branches:
    print (f"Branch {branch_name} not found!")
    return False

  if len (origin_repo.branches) > 1:
    print ("WARN: This tool will only migrate one branch")
    print ("      Multiple branches is not supported")
    return True

  return True

def initRepositories(origin_repo_path, cloned_repo_path, target_repo_path):
  """
  This is just to cleanup cloned and target repos and start fresh every time to
  avoid any sort of issues.
  """
  shutil.rmtree(cloned_repo_path, ignore_errors = True)
  shutil.rmtree(target_repo_path, ignore_errors = True)
  os.makedirs(target_repo_path, exist_ok = True)

  # init all repos (and clone origin)
  origin_repo = git.Repo(origin_repo_path)
  cloned_repo = origin_repo.clone(cloned_repo_path)
  target_repo = git.Repo.init(target_repo_path)

  return True

def scan(path):
  """
  Scans all files and folders on given path and return relative paths to all the
  files found
  """
  all_files = set()

  for root, dirs, files in os.walk(path):
    if root.startswith(os.path.join(path, '.git')):
      continue

    rpath = os.path.relpath(root, path)
    for file in files:
      file_path = os.path.join(rpath, file)
      all_files.add(file_path)

  return all_files

def fileInplaceSearchAndReplace(file_path, search_text, replace_text):
  """ Read file, replace all search_text instances by replace_text and save file

  NOTE: we can do this with memory mapped files, but since the common case
  would be with text files, we do it using read/write for simplicity/readability
  """
  search_text = search_text.encode()
  replace_text = replace_text.encode()

  with open(file_path, "r+b") as f:
    data = f.read().replace(search_text, replace_text)
    f.seek(0, os.SEEK_SET)
    f.write(data)
    
  return

def replayCommitTags(
  cloned_repo,
  target_repo,
  commit_mapping,
  authors_mapping,
  verbose
):
  """ Replay tags by looking at each tag commit and map it to the new commit
  """
  target_git = target_repo.git
  for tagref in cloned_repo.tags:
    if verbose:
      print ("Tagging:", tagref.name)

    try:    target_hexsha = commit_mapping.get (tagref.commit.hexsha, None)
    except: target_hexsha = None

    if not target_hexsha:
      if verbose:
        print(f"WARN: Cannot map tag: {tagref.name} @ {tagref.commit.hexsha}")
        print("      This tool only supports commit tags (not blob or tree tags)")
      continue

    tag = tagref.tag

    # lightweight tag
    if tag is None:
      target_git.tag(tagref.name, target_hexsha)

    # normal tag
    else:
      tagger_key = f'{tag.tagger.name} <{tag.tagger.email}>'
      tagger_name = authors_mapping.get(tagger_key, {'name' : tag.tagger.name}).get('name')
      tagger_email = authors_mapping.get(tagger_key, {'email': tag.tagger.email}).get('email')

      with target_git.custom_environment(
        GIT_AUTHOR_NAME=tagger_name,
        GIT_AUTHOR_EMAIL=tagger_email,
        GIT_AUTHOR_DATE=f"{tag.tagged_date} {tag.tagger_tz_offset}",
        GIT_COMMITTER_DATE=f"{tag.tagged_date} {tag.tagger_tz_offset}",
      ):
        if tag.message:
          target_git.tag("-a", tag.tag, "-m", tag.message, target_hexsha)
        else:
          target_git.tag(tag.tag, target_hexsha)

def multireplace(what, table_dict):
  """ Replace multiple strings in what using given search and replace table
  """
  if not table_dict:
    return what

  for search, replacement in table_dict.items():
    what = what.replace(search, replacement)
  return what

def replayCommits(
  cloned_repo_path,
  target_repo_path,
  branch_name,
  git_attributes_contents,
  authors_mapping,
  files_to_rename,
  files_to_delete,
  files_to_replace,
  verbose
):
  """
  Replay all commits on the cloned repo starting from the very first commit
  and copy the files into the new target repo, add LFS files where appropriate
  and commit them, in order, using same author, time, message, etc... but this
  time with LFS enabled
  """
  cloned_repo = git.Repo(cloned_repo_path)
  target_repo = git.Repo(target_repo_path)

  if verbose:
    print("Replaying commits:")
    print("  Cloned Repo    : ", cloned_repo_path)
    print("  Target LFS Repo: ", target_repo_path)

  # write gitattributes on the target repo
  with open(os.path.join(target_repo_path, '.gitattributes'), 'a+t') as f:
    f.write('\n')
    f.write(git_attributes_contents)

  # all commits from older to newest
  commits = list(reversed(list(cloned_repo.iter_commits(branch_name))))
  cloned_git = cloned_repo.git
  target_git = target_repo.git

  previous_files = None
  previous_commit = None
  commit_mapping = {}
  for n, commit in enumerate(commits):
    start_time = time.time()
    # perform some lookups for author/committer in case it needs to be adjusted
    author_key = f'{commit.author.name} <{commit.author.email}>'
    author_name = authors_mapping.get(author_key, {'name' : commit.author.name}).get('name')
    author_email = authors_mapping.get(author_key, {'email': commit.author.email}).get('email')

    committer_key = f'{commit.committer.name} <{commit.committer.email}>'
    committer_name = authors_mapping.get(committer_key, {'name' : commit.committer.name}).get('name')
    committer_email = authors_mapping.get(committer_key, {'email': commit.committer.email}).get('email')

    if verbose:
      date_string = datetime.utcfromtimestamp(commit.authored_date).strftime("%Y-%m-%d")
      short_message = commit.message.replace('\n', ' ').strip()[0:40]
      sys.stdout.write(f"  [{n+1:5d}/{len(commits):5d}] {date_string} {commit.hexsha[0:8]} {author_name[0:16]:<16s} {short_message:<40}...")
      sys.stdout.flush()

    cloned_git.checkout(commit.hexsha)

    # Traverse removed elements only (the others will be detected by git itself
    # when we try to do the commit)
    if not previous_commit:
      shutil.copytree (
        cloned_repo_path,
        target_repo_path,
        ignore = shutil.ignore_patterns(".git", ".git/**", ".gitattributes"),
        dirs_exist_ok = True
      )

      # TODO: decide what to do if a .gitattributes file is found
      if os.path.exists(os.path.join(cloned_repo_path, '.gitattributes')):
        print(f"WARN: Found an existing .gitattributes in the first commit: {commit.hexsha[:8]}")
        print(f"WARN: Existing .gitattributes will be ignored")

      for file in files_to_delete:
        if os.path.isfile(file):
          os.unlink(file)
          try: os.removedirs(os.path.dirname(file))
          except: pass

      for file in files_to_replace.keys():
        if os.path.isfile(file):
          what_to_replace = files_to_replace[file]
          for search, replace in what_to_replace.items():
            fileInplaceSearchAndReplace(file, search, replace)

      if files_to_rename:
        for root, dirs, files in os.walk(target_repo_path):
          for name in dirs:
            org_path = os.path.join(root, name)
            new_path = multireplace (org_path, files_to_rename)
            if org_path != new_path:
              os.renames(org_path, new_path)

        for root, dirs, files in os.walk(target_repo_path):
          for name in files:
            org_path = os.path.join(root, name)
            new_path = multireplace (org_path, files_to_rename)
            if org_path != new_path:
              os.renames(org_path, new_path)
    else:
      #for diff_del in commit.diff(previous_commit):
      for what in previous_commit.diff(commit):
        if what.a_path == '.gitattributes':
          print(f"WARN: Found an existing .gitattributes in history: commit {commit.hexsha[:8]}")
          print(f"WARN: Existing .gitattributes will be ignored")
          continue

        # print (what.change_type, what.a_path)
        match what.change_type:
          # file was added, or modified or type changed, then copy to target
          case 'A' | 'M' | 'T':
            target_rel = multireplace (what.a_path, files_to_rename)
            source_file = os.path.join(cloned_repo_path, what.a_path)
            target_file = os.path.join(target_repo_path, target_rel)

            os.makedirs(os.path.dirname(target_file), exist_ok = True)
            shutil.copy2(source_file, target_file)

            if what.a_path in files_to_delete and os.path.exists(target_file):
              os.unlink(target_file)
              try: os.removedirs(os.path.dirname(target_file))
              except: pass

            if what.a_path in files_to_replace and os.path.isfile(target_file):
              what_to_replace = files_to_replace[what.a_path]
              for search, replace in what_to_replace.items():
                fileInplaceSearchAndReplace(target_file, search, replace)

          # deleted, delete from target
          case 'D':
            if what.a_path in files_to_delete:
              # if source file is there, it should have been deleted,
              # thus we cannot delete it again
              continue

            file_path = multireplace (what.a_path, files_to_rename)
            file_path = os.path.join(target_repo_path, file_path)
            os.unlink(file_path)
            try: os.removedirs(os.path.dirname(file_path))
            except: pass

          case 'R':
            if what.a_path in files_to_delete:
              # if source file is there, it should have been deleted,
              # thus we cannot rename it
              continue

            source_rel = multireplace (what.a_path, files_to_rename)
            target_rel = multireplace (what.b_path, files_to_rename)

            source_file = os.path.join(target_repo_path, source_rel)
            target_file = os.path.join(target_repo_path, target_rel)

            os.renames(source_file, target_file)

            try:    os.removedirs(os.path.dirname(source_file))
            except: pass

            if what.b_path in files_to_delete and os.path.exsits(target_file):
              os.unlink(target_file)
              try: os.removedirs(os.path.dirname(target_file))
              except: pass

          case _:
            raise Exception ("ERROR! This shouldn't happen! (O_o)", what.change_type)

    with target_git.custom_environment(
      GIT_AUTHOR_NAME=author_name,
      GIT_AUTHOR_EMAIL=author_email,
      GIT_AUTHOR_DATE=f"{commit.authored_date} {commit.author_tz_offset}",
      GIT_COMMITTER_NAME=committer_name,
      GIT_COMMITTER_EMAIL=committer_email,
      GIT_COMMITTER_DATE=f"{commit.committed_date} {commit.committer_tz_offset}",
    ):
      # NOTE: this commit won't generate same hash, even without LFS involved
      target_git.add('.')
      target_git.commit(
        '--no-verify',
        '--allow-empty', # prevent issues in merge commits
        '--allow-empty-message', # just in case
        '-m', commit.message
      )

      commit_mapping[commit.hexsha] = target_repo.head.commit.hexsha

    previous_commit = commit

    end_time = time.time()
    if verbose:
      print (f" (took {end_time - start_time:3.3f}s)")

  replayCommitTags(
    cloned_repo,
    target_repo,
    commit_mapping,
    authors_mapping,
    verbose
  )

  # let's GC
  # if verbose:
  #   sys.stdout.write ("Cleanup & optimize git repo: reflog & gc")
  #   sys.stdout.flush()

  # start_time = time.time()
  # target_git.reflog("expire", "--expire=now", "--all")
  # target_git.gc("--prune=now", "--aggressive")

  # end_time = time.time()
  # if verbose:
  #   print (f" (took {end_time - start_time:3.3f}s)")

  return True

def looksBinary(lfs_patterns, file_name, file_size, read_stream):
  """ Returns True if given file looks binary
  """
  lfs_size_threshold = 1024*1024

  if len([p for p in lfs_patterns if fnmatch.fnmatch(file_name, p)]) > 0:
    return True

  # check files that won't be catched with patterns
  if file_size >= lfs_size_threshold:
    return True

  # looks binary?
  elif read_stream.read(1024).count(b'\0') >= 1:
    return True

  return False

def detectSensitiveFiles(file_name):
  """ Returns a list of issues or empty list if no issues are found
  """
  warnings = []
  if file_name == '.gitattributes':
    warnings.append(f".gitattributes found in history. File will be ignored! Make sure your .gitattributes contais everything needed!")

  for ext in ['.cer', '.key', '.p12', '.crt', '.pem']:
    if file_name.endswith(ext):
      warnings.append(f"File can contain sensitive info: {file_name}")

  if '%' in file_name:
    index = file_name.index('%')
    warnings.append (f"At least a file contains '%' symbol: {file_name[index:index+3]} (see history_rename_files config if you'd like to rename them)")

  return warnings

def analyzeGitRepository(repo_path, branch_name, lfs_patterns, verbose):
  """ Analyze a git repository and extract authors mapping and LFS files
  """
  repo = git.Repo(repo_path)

  # all commits from older to newest
  commits = list(reversed(list(repo.iter_commits(branch_name))))

  warnings = set()
  authors_mapping = {}
  lfs_file_commit_count = collections.Counter()
  lfs_aggregated_file_size = collections.Counter()
  lfs_files = set()
  previous_commit = None
  for n, commit in enumerate(commits):
    if verbose:
      date_string = datetime.utcfromtimestamp(commit.authored_date).strftime("%Y-%m-%d")
      short_message = commit.message.replace('\n', ' ').strip()[0:40]
      sys.stdout.write(f"\r  [{n+1:5d}/{len(commits):5d}] {date_string} {commit.hexsha[0:8]} {commit.author.name[0:16]:<16s} {short_message:<40}...")
      sys.stdout.flush()

    author_key = f'{commit.author.name} <{commit.author.email}>'
    committer_key = f'{commit.committer.name} <{commit.committer.email}>'

    authors_mapping[author_key] = {
      'name' : commit.author.name,
      'email': commit.author.email
    }

    authors_mapping[committer_key] = {
      'name' : commit.committer.name,
      'email': commit.committer.email
    }

    if previous_commit is None:
      for blob in commit.tree.traverse():
        if blob.type != 'blob':
          continue

        if looksBinary(lfs_patterns, blob.path, blob.size, blob.data_stream):
          lfs_aggregated_file_size[blob.path] += blob.size
          lfs_file_commit_count[blob.path]+=1
          lfs_files.add(blob.path)

        warnings.update(detectSensitiveFiles(blob.path))
    else:
      for what in previous_commit.diff(commit):
        # maybe a file is added first as text but later to binary, and still
        # we'd like to treat it as binary
        if what.change_type == 'A' or what.change_type == 'M':
          if (
            what.b_path in lfs_files
            or looksBinary(lfs_patterns, what.b_path, what.b_blob.size, what.b_blob.data_stream)
          ):
            lfs_file_commit_count[what.b_path]+=1
            lfs_aggregated_file_size[what.b_path] += what.b_blob.size
            lfs_files.add(what.b_path)
          warnings.update (detectSensitiveFiles(what.b_path))

    previous_commit = commit

  # Warn if aggregated file size is more than 50MB, just for the user to be aware
  for name, size in lfs_aggregated_file_size.most_common():
    if size > 50*1024*1024:
      warnings.add (f"Aggregated history of {name} is {size/(1024*1024):.2f}MB (in {lfs_file_commit_count[name]} commits)")

  # from all files, get only the ones that won't be matched by the existing lfs patterns
  extra_lfs_patterns = set()
  for file_name in lfs_files:
    if len([p for p in lfs_patterns if fnmatch.fnmatch(file_name, p)]) > 0:
      continue
    extra_lfs_patterns.add (file_name)

  if verbose:
    print ("")

  return {
    'authors' : authors_mapping,
    'warnings' : list(sorted(warnings)),
    'sample:history_rename_files' : {
      '%23': '#',
      '%40': '@'
    },
    'sample:history_delete_files' : [
      'path/file/to/be/removed.json'
    ],
    'sample:history_replace_file_contents' : {
      'path/to/secrets.json' : {
        'search_string' : 'replacement_string'
      }
    },
    'lfs_patterns' : KW_DEFAULT,
    'extra_lfs_patterns' : sorted(list(extra_lfs_patterns))
  }

def mainAnalyzeRepo(origin_repo_path, branch, config_file, verbose):
  """ Main entry point for analyzing repo
  """
  print (f"Analyzing repo: {origin_repo_path}")

  lfs_patterns = getPatternsFromPatternMultiline(GITATTRIBUTES_DEFAULT_LFS_PATTERNS)
  if os.path.exists(config_file):
    with open(config_file, "rt") as f:
      data = json.load(f)

    # preserve LFS patterns
    lfs_patterns = data.get('lfs_patterns', KW_DEFAULT)
    if isinstance(lfs_patterns, list):
      try:
        defaultOffset = lfs_patterns.index(KW_DEFAULT)
        lfs_patterns[defaultOffset:defaultOffset+1] = getPatternsFromPatternMultiline(GITATTRIBUTES_DEFAULT_LFS_PATTERNS)
      except:
        pass # default not found!

  config = analyzeGitRepository(origin_repo_path, branch, lfs_patterns, verbose)

  print (f"Writing config file: {config_file}")

  if os.path.exists(config_file):
    with open(config_file, "rt") as f:
      org_config = json.load(f)
      for key, value in org_config.get('authors', {}).items():
        config['authors'][key] = value

      keys_to_preserve = ['lfs_patterns', 'history_rename_files', 'history_replace_file_contents', 'history_delete_files']
      for k in keys_to_preserve:
        if k in org_config:
          config[k] = org_config.get(k, config.get(k, None))
          config.pop (f'sample:{k}', None)

  with open(config_file, "wt") as f:
    json.dump(config, f, indent=2, ensure_ascii=False)

  return True

def main():
  """
  Main application

  Parses args, checks requirements, initializes everything and replays
  all commits with LFS
  """
  parser = argparse.ArgumentParser(
    prog='migrate2gitlfs.py',
    formatter_class=argparse.RawTextHelpFormatter,
    description="""
Quickly transform a git repository into git-lfs. Works only with local repos.
Allows analyzing repo and then renaming authors, choosing LFS patterns and
selecting files to be deleted from history
    """,
    epilog="""
Examples:
  $ python3 migrate2gitlfs.py analyze --config config.json my-git-repo-folder
  $ python3 migrate2gitlfs.py migrate --config config.json  my-git-repo-folder
    """
  )

  subparsers = parser.add_subparsers(
    dest='command',
    required = True,
    help='sub-commands help'
  )

  parser_analyze = subparsers.add_parser('analyze', help='Analyzes git history and generates a JSON file with authors mapping and LFS candidate patterns that you can tweak')
  parser_migrate = subparsers.add_parser('migrate', help='Migrates git history to LFS using given config file (or using default LFS patterns)')

  for p in [parser_analyze, parser_migrate]:
    p.add_argument('--branch', default='master', help="Which is the branch to migrate")
    p.add_argument('--config', default='', help="Use JSON configuration file with authors & lfs patterns. Create config with --analyze")
    p.add_argument('-v', '--verbose', action='store_true')
    p.add_argument('origin_repo_path')

  args = parser.parse_args()

  origin_repo_path = args.origin_repo_path
  if not os.path.exists(origin_repo_path):
    local_repo = os.path.abspath(os.path.basename(origin_repo_path))
    if not os.path.exists(local_repo):
      print (f"Cloning remote desktop into: {local_repo}")
      subprocess.check_call(['git', 'clone', '--mirror', args.origin_repo_path, local_repo])
    origin_repo_path = local_repo

  origin_repo_path = os.path.abspath(origin_repo_path)
  cloned_repo_path = origin_repo_path + '-clone'
  target_repo_path = origin_repo_path + '-lfs'
  default_config_path = origin_repo_path + '-config.json'

  authors_mapping = {}
  files_to_delete = set()
  files_to_replace = {}
  git_attributes_content = gitAttributesLfsFromPatterns(GITATTRIBUTES_DEFAULT_LFS_PATTERNS)

  if not args.config:
    args.config = default_config_path

  if args.command == 'analyze':
    mainAnalyzeRepo(
      origin_repo_path,
      branch = args.branch,
      config_file = args.config,
      verbose = args.verbose
    )
    sys.exit(0)
  elif args.command != 'migrate':
    print ("Only analyze or migrate subcommands are supported")
    sys.exit(-1)

  # if no analyze is passed, we try to rebuild everything, read config
  if args.config and os.path.exists(args.config):
    with open(args.config, "rt") as f:
      data = json.load(f)

    authors_mapping = data.get('authors', {})

    files_to_rename = data.get('history_rename_files', {})
    files_to_delete = set(data.get('history_delete_files', []))
    files_to_replace = data.get('history_replace_file_contents', {})

    lfs_patterns = data.get('lfs_patterns', KW_DEFAULT)
    git_attributes_content = gitAttributesLfsFromPatterns(lfs_patterns)

    extra_lfs_patterns = data.get('extra_lfs_patterns', None)
    if extra_lfs_patterns:
      extra = gitAttributesLfsFromPatterns('\n'.join(extra_lfs_patterns))
      git_attributes_content = gitAttributesMergeDumb (
        git_attributes_content,
        extra,
        "\n# Project Specific"
      )

  if not checkRequirements(origin_repo_path, args.branch):
    print("Exit: Some requirements have not been met. Please review other errors.")
    sys.exit(-1)

  if not initRepositories(origin_repo_path, cloned_repo_path, target_repo_path):
    print("Exit: Problem initializing the reposotiries")
    sys.exit(-2)

  if not replayCommits(
    cloned_repo_path,
    target_repo_path,
    args.branch,
    git_attributes_content,
    authors_mapping,
    files_to_rename,
    files_to_delete,
    files_to_replace,
    args.verbose
  ):
    print ("Exit: Could not replay commits \\_/(O_o)\\_/")
    sys.exit(-3)

  if args.verbose:
    print("Your LFS repo is ready:")
    print(target_repo_path)
    print("Next steps:")
    print(f"  git remote add origin git@server.com:path/{os.path.basename(target_repo_path)}.git")
    print(f"  git branch -M {args.branch}")
    print(f"  git push -u origin {args.branch}")

  # everything ok!
  sys.exit(0)

if __name__ == '__main__':
  main()