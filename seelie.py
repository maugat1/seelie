#!/usr/bin/python3

"""
Synchronizes paths listed in a config file.

author: Malcolm Augat <ma5ke@virginia.edu>
version: 0.2.2
"""

import xml.etree.ElementTree as etree
import sys
import os
import subprocess
import socket
import time

def color_print(*values, color=None, sep=' ', end='\n', file=sys.stdout,
        flush=False):
    """
    Prints the given arguments in the given color.

    Keyword arguments:
    color -- a color name string or None (default color)
    """
    if color == None:
        color = '\033[0m'
    elif color.lower() == 'black':
        color = '\033[90m'
    elif color.lower() == 'red':
        color = '\033[91m'
    elif color.lower() == 'green':
        color = '\033[92m'
    elif color.lower() == 'yellow':
        color = '\033[93m'
    elif color.lower() == 'blue':
        color = '\033[94m'
    elif color.lower() == 'purple':
        color = '\033[95m'
    elif color.lower() == 'cyan':
        color = '\033[96m'
    elif color.lower() == 'white':
        color = '\033[97m'
    else:
        raise ValueError("Unknown color '%s'" % (color))
    print(color, sep='', end='', file=file, flush=flush)
    print(*values, sep=sep, end=end, file=file, flush=flush)
    print('\033[0m', sep='', end='', file=file, flush=flush)

def project_print(*args, **kwargs):
    """
    Prints the given arguments in colors for projects
    """
    color_print(*args, color=None, **kwargs)

def path_print(*args, **kwargs):
    """
    Prints the given arguments in colors for paths
    """
    color_print(*args, color='blue', **kwargs)

def reference_print(*args, **kwargs):
    """
    Prints the given arguments in colors for references
    """
    color_print(*args, color='cyan', **kwargs)

def unknown_print(*args, **kwargs):
    """
    Prints the given arguments in colors for uknown
    """
    color_print(*args, color='purple', **kwargs)

def success_print(*args, **kwargs):
    """
    Prints the given arguments in success colors
    """
    color_print(*args, color='green', **kwargs)

def error_print(*args, **kwargs):
    """
    Prints the given arguments in error colors
    """
    color_print(*args, color='red', **kwargs)

class Seelie(object):

    """
    Abstract base class for Seelie syncing objects
    """

    def __init__(self, tree, sync=None, verbose=False):
        """
        Initializes the Seelie object.

        Keyword arguments:
        tree -- the root of a seelie XML tree
        sync -- a dictionary mapping syncing tool strings (e.g., "git", "rsync")
            to Sync objects, or None for the default dictionary
        verbose -- warns the user of potential errors if True
        """
        # dictionary of synchronizers
        if sync is None:
            sync = {
                    'git': GitSync(),
                    'rsync': RSync(),
                    None: GitSync(),
                    }
        self.sync = sync
        # XML tree
        self.tree = tree
        if(self.tree.getroot().tag.lower() != 'seelie'):
            raise TypeError('XML tree root is not seelie')
        # list of projects
        self.projects = self.xml_to_projects(self.tree, verbose=verbose)
        # dict of project names to indices
        self.names = dict(zip([p.name for p in self.projects],
            range(0, len(self.projects))))
        if(None in self.names):
            self.names.pop(None)
        # list of automatic projects (the default list to use)
        self.auto = [p.name for p in self.projects if p.auto]

    @staticmethod
    def xml_to_projects(tree, verbose=False):
        """
        Reads the seelie projects from the given xml tree and returns a list of
        SeelieProject objects.

        Keyword arguments:
        tree -- the root of a seelie XML tree
        verbose -- warns the user of potential errors if True
        """
        i = 0
        projs = []
        for proj in tree.getroot():
            i = i+1
            if(proj.tag.lower() != 'project'):
                if(verbose):
                    print("Ignored seelie child %i, tag='%s'" % (i, proj.tag),
                            file=sys.stderr)
                continue
            # get the list of objects for it
            cur = SeelieProject(proj, verbose=verbose, i=i)
            projs.append(cur)
        return projs
    
    def apply(self, mode, names=None, verbose=False, *args, **kwargs):
        """
        Depending on the mode either updates, pushes, or resolves the projects
        specified by names (all by default).
        Further arguments are passed to the synchronizer.

        Keyword arguments:
        mode -- a string, one of "update", "push", or "resolve"
        names -- a list of project names or indices, or None for all automatic
            projects (default)
        verbose -- printing level
        """
        # already visited paths and projects
        visited_paths = set()
        visited_projects = [False] * len(self.projects)
        # paths and projects with errors
        error_paths = set()
        error_projects = [False] * len(self.projects)
        unknown_projects = set()
        # list of project indices to deal with
        if(names is None):
            projects = [self.names[n] for n in self.auto]
        else:
            projects = [self.names[n] for n in names if n in self.names]
            unknown_projects |= set([n for n in names if(not n in self.names)])

        def apply_project(i, *args, **kwargs):
            """
            Helper function to iterate over all paths and references in a
            single project. Takes the appropriate action based on the mode (as
            set in the parent function), and updates the error and visitied
            project information.
            Further arguments are passed to the synchronizer.

            Keyword arguments:
            i -- index of the project
            """
            # check that it hasn't already been dealt with
            if(visited_projects[i]):
                return error_projects[i]
            visited_projects[i] = True
            # handle all items in the project
            any_error = False
            if(verbose):
                name = self.projects[i].name or ('project #%d' % (i+1))
                project_print(name)
            # iterate over paths/references in the project
            for item in self.projects[i]:
                error = False
                if(isinstance(item, SeeliePath)):
                    # check if already visited, otherwise apply the function
                    if(item.path in visited_paths):
                        error = (item.path in error_paths)
                    else:
                        # print the name
                        if(verbose == 1):
                            path_print('\t', item.path, sep='', end='')
                            project_print('... ', sep='', end='', flush=True)
                        # apply the appropriate function and tool
                        visited_paths.add(item.path)
                        sync = self.sync[item.tool]
                        if(mode == 'update'):
                            error = sync.update(item.path, src=item.origin,
                                    verbose=(verbose > 1), *args, **kwargs)
                        elif(mode == 'push'):
                            error = sync.push(item.path, dest=item.origin,
                                    verbose=(verbose > 1), *args, **kwargs)
                        elif(mode == 'resolve'):
                            error = sync.resolve(item.path,
                                    verbose=(verbose > 1), *args, **kwargs)
                        else:
                            raise ValueError("unknown mode: '%s'" % (mode))
                        # print the name if needed
                        if(verbose > 1):
                            path_print('\t', item, " ", sep='', end='')
                        if(error):
                            error_paths.add(item)
                            # print the status
                            if(verbose):
                                error_print('failed!')
                        elif(verbose):
                            success_print('ok')
                elif(isinstance(item, SeelieRef)):
                    if(item.name in self.names):
                        error = apply_project(self.names[item.name], *args,
                                **kwargs)
                    else:
                        unknown_projects.add(item.name)
                        error = True
                else:
                    TypeError("Unknown project type '%s'" % type(item).__name__)
                any_error = any_error or error
            error_projects[i] = any_error
            return any_error

        # iterate over the projects
        for i in projects:
            apply_project(i, *args, **kwargs)
        if(verbose):
            # list the unknown projects and references
            if(unknown_projects):
                unknown_print("unknown projects or references:")
                for name in sorted(unknown_projects):
                    unknown_print("\t%s" % (name), file=sys.stderr)
            # projects with errors
            if(names is None):
                errors = [(self.projects[i].name or
                    ('seelie project #%d' % (i+1)))
                        for i in projects if error_projects[i]]
            else:
                errors = []
                for n in names:
                    if (n in self.projects) and error_projects[self.names[n]]:
                        errors.append(n)
            if(errors):
                error_print("projects with errors:", file=sys.stderr)
                for name in errors:
                    error_print("\t%s" % (name), file=sys.stderr)
            # paths with errors
            if(error_paths):
                error_print("repositories with errors:", file=sys.stderr)
                for path in sorted([x.path for x in error_paths]):
                    error_print("\t%s" % (path), file=sys.stderr)

    def update(self, names=None, verbose=False, merge=False):
        """
        Updates the projects given in names (all by default).

        Keyword arguments:
        names -- a list of project names or indices, or None for all projects
            (default)
        verbose -- printing level
        merge -- attempts to merge branches if true, rebases otherwise (default)
        """
        self.apply(mode='update', names=names, verbose=verbose, merge=merge)

    def push(self, names=None, verbose=False):
        """
        Commits changes and pushes the projects given in names (all by default).

        Keyword arguments:
        names -- a list of project names or indices, or None for all projects
            (default)
        verbose -- printing level
        """
        self.apply(mode='push', names=names, verbose=verbose)

    def resolve(self, names=None, verbose=False):
        """
        Resolves conflicts in the projects specified by names (all by default).

        Keyword arguments:
        names -- a list of project names or indices, or None for all projects
            (default)
        verbose -- printing level
        """
        self.apply(mode='resolve', names=names, verbose=verbose)


class Sync(object):

    """
    Abstract base class for synchronizers.
    """

    @staticmethod
    def update(path, merge=False, verbose=False):
        raise NotImplementedError("abstract class")

    @staticmethod
    def push(path, verbose=False):
        raise NotImplementedError("abstract class")

    @staticmethod
    def resolve(path):
        raise NotImplementedError("abstract class")


class GitSync(object):

    """
    Synchronizes paths using git.
    """

    @staticmethod
    def update(path, src=None, merge=False, verbose=False):
        """
        Update a path, pulling any changes. Returns False if no errors.

        Keyword arguments:
        path -- the path to update
        src -- where to pull from, set to "origin" if src is None
        merge -- attempts to merge branches if true, rebases otherwise (default)
        verbose -- printing level
        """
        if src is None:
            src = "origin"
        # change to the repository path
        error = False
        here = os.getcwd()
        try:
            os.chdir(os.path.expanduser(path))
        except IOError:
            error = True
        # set the pipes and printing color
        if verbose:
            out = sys.stdout
            err = sys.stderr
            print('\033[97m', sep='', end='', file=out, flush=True)
        else:
            out = subprocess.DEVNULL
            err = subprocess.DEVNULL
        # update the repository and check the results
        # TODO: log the output using the stdout and stderr arguments
        if merge:
            error = error or subprocess.call(('git', 'pull', src, 'master'),
                    stdout=out, stderr=err)
        else:
            error = error or subprocess.call(('git', 'pull', '--rebase', src,
                'master'), stdout=out, stderr=err)
        # reset the printing color
        if verbose:
            print('\033[0m', sep='', end='', file=out, flush=True)
        # change back to the current path
        os.chdir(here)
        return error

    @staticmethod
    def push(path, dest="origin", verbose=False):
        """
        Adds and commits all changes, then pushes the commit.

        Keyword arguments:
        path -- the path to push
        dest -- where to push to, set to "origin" if dest is None
        verbose -- printing level
        """
        if dest is None:
            dest = "origin"
        # change to the repository path
        error = False
        here = os.getcwd()
        try:
            os.chdir(os.path.expanduser(path))
        except IOError:
            error = True
        # set the pipes and printing color
        if verbose:
            out = sys.stdout
            err = sys.stderr
            print('\033[97m', sep='', end='', file=out, flush=True)
        else:
            out = subprocess.DEVNULL
            err = subprocess.DEVNULL
        # add all changes to the repository
        error = error or subprocess.call(('git', 'add', '--all'),
                stdout=out, stderr=err)
        # see if there are any changes
        status = 'changes?'
        try:
            if(not error):
                status = subprocess.check_output(('git', 'status',
                    '--porcelain'), stderr=err)
        except subprocess.CalledProcessError:
            error = True
        # only continue if there are changes to commit
        if(status):
            # commit to the repository
            error = error or subprocess.call(('git', 'commit', '-m',
                'seelie commit from %s at %s' % (
                    socket.gethostname(), time.strftime('%F %T %Z'))),
                stdout=out, stderr=err)
            # push the changes
            # TODO: log the output using the stdout and stderr arguments
            error = error or subprocess.call(('git', 'push', dest, 'master'),
                    stdout=out, stderr=err)
        # reset the printing color
        if verbose:
            print('\033[0m', sep='', end='', file=out, flush=True)
        # change back to the current path
        os.chdir(here)
        return error

    @staticmethod
    def resolve(path, verbose=False):
        """
        Resolves changes 

        Keyword arguments:
        path -- the path to push
        verbose -- printing level

        TODO: write this
        """
        raise NotImplementedError("can't resolve yet...")


class RSync(object):

    """
    Synchronizes paths using rsync.
    """

    @staticmethod
    def update(path, src, merge=False, verbose=False):
        """
        Update a path, pulling any changes. Returns False if no errors.

        Keyword arguments:
        path -- the path to update
        merge -- ignored
        verbose -- printing level
        """
        cmd = "rsync"
        flags = "-au"
        # TODO: check that 
        opts = "--delete"
        if verbose:
            flags += "v"
        # set the pipes and printing color
        if verbose:
            out = sys.stdout
            err = sys.stderr
            print('\033[97m', sep='', end='', file=out, flush=True)
        else:
            out = subprocess.DEVNULL
            err = subprocess.DEVNULL
        try:
            # update the path
            # TODO: log the output using the stdout and stderr arguments
            error = subprocess.call((cmd, flags, opts, src, path), stdout=out,
                    stderr=err)
        except OSError as emsg:
            error = True
            if verbose:
                error_print(emsg)
        return error

    @staticmethod
    def push(path, dest, verbose=False):
        """
        Adds and commits all changes, then pushes the commit.

        Keyword arguments:
        path -- the path to push
        verbose -- printing level
        """
        cmd = "rsync"
        flags = "-au"
        opts = "--delete"
        if verbose:
            flags += "v"
        # set the pipes and printing color
        if verbose:
            out = sys.stdout
            err = sys.stderr
            print('\033[97m', sep='', end='', file=out, flush=True)
        else:
            out = subprocess.DEVNULL
            err = subprocess.DEVNULL
        try:
            # update the path
            # TODO: log the output using the stdout and stderr arguments
            error = subprocess.call((cmd, flags, opts, path, dest), stdout=out,
                    stderr=err)
        except OSError as emsg:
            error = True
            if verbose:
                error_print(emsg)
        return error

    @staticmethod
    def resolve(path, verbose=False):
        """
        Resolves changes 

        Keyword arguments:
        path -- the path to push
        verbose -- printing level

        TODO: write this
        """
        raise NotImplementedError("can't resolve yet...")

class SeeliePath(object):

    """
    Holds information about a path to be synched (folder or repository)
    """
    
    def __init__(self, path, tool=None, origin=None):
        self.path = os.path.normpath(os.path.expanduser(path))
        if(os.path.isdir(self.path)):
            self.path = os.path.join(self.path, "")
        self.tool = tool
        self.origin = origin

    def __str__(self):
        return str(self.path)


class SeelieRef(object):

    """
    A reference to another project
    """
    
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return str(self.name)


class SeelieProject(object):

    """
    Container class with information about a project to be synchronized,
    usually with one or more associated paths or references.
    """

    def __init__(self, node, verbose=False, i=0):
        self.name = None
        self.items = []
        # automatically update this project?
        self.auto = node.attrib.get("auto", "true")
        if(self.auto.lower() == "false" or self.auto == "0"):
            self.auto = False
        else:
            self.auto = True
        for child in node:
            # set the name
            if(child.tag.lower() == 'name'):
                if(verbose and (not self.name is None)):
                    print("Duplicate name definition for project #%d:" % (i),
                            "'%s' and '%s'" % (self.name, child.text),
                            file=sys.stderr)
                self.name = child.text
            elif(child.tag.lower() == 'path'):
                # tool to use
                tool = child.attrib.get('tool', None)
                # origin
                origin = child.attrib.get('origin', None)
                # add the path to the project
                self.items.append(SeeliePath(child.text, tool, origin))
            elif(child.tag.lower() == 'reference'):
                # add the reference to the project
                self.items.append(SeelieRef(child.text))
            elif verbose:
                print("Ignored project #%d child with tag '%s'"
                        % (i, child.tag), file=sys.stderr)
        if(verbose and (self.name is None)):
            print("No name set for project #%d" % (i), file=sys.stderr)

    def __getitem__(self, key):
        return self.items[key]

    def __iter__(self):
        return iter(self.items)


if __name__ == '__main__':
    import argparse

    # modes
    update = 'update'
    merge = 'merge'
    push = 'push'
    resolve = 'resolve'

    # default arguments
    projects = None
    config_file = ['~/.seelie/config.xml']
    mode = update
    verbose = 1
    merge = False

    # set up argument parsing
    parser = argparse.ArgumentParser(description="Updates the given git "
            "repositories based on the config file")
    parser.add_argument("projects", metavar="PROJECT", nargs="*",
            help="projects to update, defaults to all automatic projects")
    parser.add_argument("-c", "--config", metavar="FILE", nargs=1,
            default=config_file, help=("XML configuration file with project "
                "definitions. Default is '%s'" % (config_file[0])))
    parser.add_argument("-u", "--update", dest="mode", action="store_const",
            const=update, default=update,
            help="update projects without merging")
    parser.add_argument("-m", "--merge", dest="mode", action="store_const",
            const=update, default=update,
            help="update projects and merges changes")
    parser.add_argument("-p", "--push", dest="mode", action="store_const",
            const=push, help="commit and push changes in projects")
    parser.add_argument("-r", "--resolve", dest="mode", action="store_const",
            const=resolve, help="resolve conflicts in projects")
    parser.add_argument("-v", "--verbose", dest="verbose", action="count",
            default=verbose, help="increments the verbosity level. At level 1,"
            " status messages are printed. At level 2, some shell output is "
            "also printed. Defaults to level 1.")
    parser.add_argument("-q", "--quiet", dest="verbose", action="store_false",
            help="decrements the verbosity level. See verbose for more info.")
    args = parser.parse_args()

    # read the arguments
    projects = args.projects or projects
    config_file = os.path.expanduser(args.config[0])
    mode = args.mode
    verbose = args.verbose

    # read the configuration XML file
    tree = etree.parse(config_file)
    seelie = Seelie(tree, verbose=verbose)

    # run the action
    if(mode == update):
        # update
        seelie.update(projects, verbose=verbose, merge=False)
    elif(mode == merge):
        # update
        seelie.update(projects, verbose=verbose, merge=True)
    elif(mode == push):
        # push
        seelie.push(projects, verbose=verbose)
    elif(mode == resolve):
        # resolve
        seelie.resolve(projects, verbose=verbose)
    else:
        ValueError("unknown mode: '%s'" % (mode))
