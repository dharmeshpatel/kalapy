import os, sys
from optparse import OptionParser, make_option

from rapido.utils.implib import import_module


__all__ = ['CommandError', 'BaseCommand', 'get_commands', 'get_command']


_commands = {}
_loaded = False

def load_commands():
    """Import all command modules.
    """
    global _loaded
    if not _loaded:
        cmddir = os.path.join(os.path.dirname(__file__), 'commands')
        mods = [f[:-3] for f in os.listdir(cmddir) if f.endswith('.py') and not f.startswith('_')]
        for m in mods:
            import_module(m, 'rapido.admin.commands')
        _loaded = True
    return _commands

def get_commands(scope):

    commands = load_commands()

    [commands.pop(k) for k, v in commands.items() if v.scope != scope]

    commands = commands.items()
    commands.sort(lambda a, b: cmp(a[0], b[0]))
    return commands


def get_command(name):
    try:
        return load_commands()[name]
    except KeyError:
        print "Unknown command: %s" % name
        print "Type '%s help' for usage" % sys.argv[0]
        sys.exit(1)


class CommandError(Exception):
    pass


class CommandType(type):

    def __init__(cls, name, bases, attrs):
        super(CommandType, cls).__init__(name, bases, attrs)

        if "options" in attrs:
            cls.options = CommandType.merge_options(bases, attrs["options"])

        if name != "BaseCommand" and "name" in attrs:
            _commands[attrs["name"]] = cls

    @staticmethod
    def merge_options(bases, options):
        opts = []
        for base in bases:
            for op in getattr(base, "options", []):
                if op not in opts:
                    opts.append(op)
        opts.extend(options)
        return opts


class BaseCommand(object):
    """Base class for implementing commands. The commands will be available
    to the project or package admin scripts depending on the defined scope of
    the command.

    Attributes:
        name: name of the command
        help: help string for the command
        args: can be used in `usages` string
        scope: one of `package` or `project` else available in both the scopes
        options: command options
        exclusive: list of options which are mutually exclusive

    methods:
        print_help: print help for the command and exit
        error: raise command error
        execute: this method will be called when command is executed
    """

    __metaclass__ = CommandType

    name = ""
    help = ""
    args = ""
    scope = ""

    options = (
        make_option('-v', '--verbose', help='Verbose output.', 
            action='store_true', default=False),
    )
    exclusive = ()

    def __init__(self):
        self.verbose = False
        self.parser = OptionParserEx(prog=os.path.basename(sys.argv[0]),
                usage=self.usage,
                #add_help_option=False,
                option_list=self.options)
        self.parser.exclusive = self.exclusive

    @property
    def usage(self):
        usage = "%%prog %s [options] %s" % (self.name, self.args)
        if self.help:
            usage = "%s\n\n%s" % (usage, self.help)
        if len(self.exclusive):
            usage = "%s\nOptions %s are mutually exclusive." % (usage, ", ".join(self.exclusive))
        return usage

    def print_help(self):
        self.parser.print_help()
        sys.exit(1)

    def error(self, message):
        self.parser.error(message)

    def run(self, argv):
        options, args = self.parser.parse_args(argv[2:])
        self.verbose = options.verbose
        try:
            self.execute(*args, **options.__dict__)
        except CommandError, e:
            print "Error: %s\n" % (str(e))
            sys.exit(1)

    def execute(self, *args, **options):
        raise NotImplementedError


class OptionParserEx(OptionParser):

    exclusive = None

    def parse_args(self, args=None, values=None):
        result = OptionParser.parse_args(self, args, values)
        if self.exclusive:
            x = set([self.get_option(o) for o in self.exclusive])
            y = set([self.get_option(o) for o in args if o.startswith('-')])
            if len(x - y) != len(x) - 1:
                self.print_help()
                sys.exit(1)
        return result
