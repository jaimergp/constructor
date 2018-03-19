import os
import sys
import subprocess
from jinja2 import BaseLoader, Environment, FileSystemLoader, TemplateError

from conda_build import utils
from conda_build.os_utils import external

from constructor.exceptions import UnableToParse


# adapted from conda-build
class FilteredLoader(BaseLoader):
    """
    A pass-through for the given loader, except that the loaded source is
    filtered according to any metadata selectors in the source text.
    """

    def __init__(self, unfiltered_loader, content_filter):
        self._unfiltered_loader = unfiltered_loader
        self.list_templates = unfiltered_loader.list_templates
        self.content_filter = content_filter

    def get_source(self, environment, template):
        loader = self._unfiltered_loader
        contents, filename, uptodate = loader.get_source(environment, template)
        filtered_contents = self.content_filter(contents)
        return filtered_contents, filename, uptodate


# adapted from conda-build
def render_jinja(data, directory, content_filter):
    loader = FilteredLoader(FileSystemLoader(directory), content_filter)
    env = Environment(loader=loader)
    env.globals['environ'] = meta_vars(directory)
    env.globals['PY_VERSION'] = '{}.{}'.format(*sys.version_info[:2])
    try:
        template = env.from_string(data)
        rendered = template.render()
    except TemplateError as ex:
        raise UnableToParse(original=ex)
    return rendered


def meta_vars(repo_dir):
    d = os.environ.copy()
    for i in range(5):
        pathblocks = [repo_dir] + ['..'] * i + ['.git']
        git_dir = os.path.join(*pathblocks)
        if os.path.exists(git_dir):
            break
    else:
        return d
    if not isinstance(git_dir, str):
        # On Windows, subprocess env can't handle unicode.
        git_dir = git_dir.encode(sys.getfilesystemencoding() or 'utf-8')

    git_exe = external.find_executable('git')
    if git_exe:
        d.update(get_git_info(git_exe, git_dir, False))
    return d

# Copied from conda_build.environ


def get_git_info(git_exe, repo, debug):
    """
    Given a repo to a git repo, return a dictionary of:
      GIT_DESCRIBE_TAG
      GIT_DESCRIBE_NUMBER
      GIT_DESCRIBE_HASH
      GIT_FULL_HASH
      GIT_BUILD_STR
    from the output of git describe.
    :return:
    """
    d = {}
    log = utils.get_logger(__name__)

    if debug:
        stderr = None
    else:
        FNULL = open(os.devnull, 'w')
        stderr = FNULL

    # grab information from describe
    env = os.environ.copy()
    env['GIT_DIR'] = repo
    keys = ["GIT_DESCRIBE_TAG", "GIT_DESCRIBE_NUMBER", "GIT_DESCRIBE_HASH"]

    try:
        output = utils.check_output_env([git_exe, "describe", "--tags", "--long", "HEAD"],
                                        env=env, cwd=os.path.dirname(repo),
                                        stderr=stderr).splitlines()[0]
        output = output.decode('utf-8')
        parts = output.rsplit('-', 2)
        if len(parts) == 3:
            d.update(dict(zip(keys, parts)))
    except subprocess.CalledProcessError:
        msg = (
            "Failed to obtain git tag information.\n"
            "Consider using annotated tags if you are not already "
            "as they are more reliable when used with git describe."
        )
        log.debug(msg)

    try:
        # get the _full_ hash of the current HEAD
        output = utils.check_output_env([git_exe, "rev-parse", "HEAD"],
                                        env=env, cwd=os.path.dirname(repo),
                                        stderr=stderr).splitlines()[0]
        output = output.decode('utf-8')

        d['GIT_FULL_HASH'] = output
    except subprocess.CalledProcessError as error:
        log.debug("Error obtaining git commit information.  Error was: ")
        log.debug(str(error))

    # set up the build string
    if "GIT_DESCRIBE_NUMBER" in d and "GIT_DESCRIBE_HASH" in d:
        d['GIT_BUILD_STR'] = '{}_{}'.format(d["GIT_DESCRIBE_NUMBER"],
                                            d["GIT_DESCRIBE_HASH"])

    # issues on Windows with the next line of the command prompt being recorded here.
    assert not any("\n" in value for value in d.values())


    return d
