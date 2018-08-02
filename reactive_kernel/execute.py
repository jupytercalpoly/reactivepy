import getpass
import sys

from IPython.core import release
from ipykernel.kernelbase import Kernel as KernelBase
from ipykernel.zmqshell import ZMQInteractiveShell
from ipython_genutils.py3compat import builtin_mod, PY3, unicode_type, safe_unicode
from IPython.utils.tokenutil import token_at_cursor, line_at_cursor
from traitlets import Instance, Type, Any, List, Bool
from ipykernel.ipkernel import IPythonKernel
from ipykernel.comm import CommManager


class ExecuteKernel(KernelBase):
    shell = Instance('IPython.core.interactiveshell.InteractiveShellABC',
                     allow_none=True)
    shell_class = Type(ZMQInteractiveShell)

    user_module = Any()
    def _user_module_changed(self, name, old, new):
        if self.shell is not None:
            self.shell.user_module = new

    user_ns = Instance(dict, args=None, allow_none=True)
    def _user_ns_changed(self, name, old, new):
        if self.shell is not None:
            self.shell.user_ns = new
            self.shell.init_user_ns()


    def __init__(self, **kwargs):
        super(ExecuteKernel, self).__init__(**kwargs)
        
        #self.shell = self.shell_class

        # Initialize the InteractiveShell subclass
        self.shell = self.shell_class.instance(parent=self,
            profile_dir = self.profile_dir,
            user_module = self.user_module,
            user_ns     = self.user_ns,
            kernel      = self,
        )

        self.shell.displayhook.session = self.session
        self.shell.displayhook.pub_socket = self.iopub_socket
        self.shell.displayhook.topic = self._topic('execute_result')
        self.shell.display_pub.session = self.session
        self.shell.display_pub.pub_socket = self.iopub_socket
        self.comm_manager = CommManager(parent=self, kernel=self)

        self.shell.configurables.append(self.comm_manager)
        comm_msg_types = [ 'comm_open', 'comm_msg', 'comm_close' ]
        for msg_type in comm_msg_types:
            self.shell_handlers[msg_type] = getattr(self.comm_manager, msg_type)
        
    
    def _forward_input(self, allow_stdin=False):
        """Forward raw_input and getpass to the current frontend.
        via input_request
        """
        self._allow_stdin = allow_stdin

        if PY3:
            self._sys_raw_input = builtin_mod.input
            builtin_mod.input = self.raw_input
        else:
            self._sys_raw_input = builtin_mod.raw_input
            self._sys_eval_input = builtin_mod.input
            builtin_mod.raw_input = self.raw_input
            builtin_mod.input = lambda prompt='': eval(self.raw_input(prompt))
        self._save_getpass = getpass.getpass
        getpass.getpass = self.getpass

    def _restore_input(self):
        """Restore raw_input, getpass"""
        if PY3:
            builtin_mod.input = self._sys_raw_input
        else:
            builtin_mod.raw_input = self._sys_raw_input
            builtin_mod.input = self._sys_eval_input

        getpass.getpass = self._save_getpass


    def do_execute(self, code, silent, store_history=True,
                   user_expressions=None, allow_stdin=False):
        shell = self.shell # we'll need this a lot here

        self._forward_input(allow_stdin)

        reply_content = {} #return a dictionary
        try:
            res = shell.run_cell(code, store_history=store_history, silent=silent)
        finally:
            self._restore_input()

        if res.error_before_exec is not None:
            err = res.error_before_exec
        else:
            err = res.error_in_exec

        if res.success:
            reply_content[u'status'] = u'ok'
        else:
            reply_content[u'status'] = u'error'

            reply_content.update({
                u'traceback': shell._last_traceback or [],
                u'ename': unicode_type(type(err).__name__),
                u'evalue': safe_unicode(err),
            })

            # FIXME: deprecated piece for ipyparallel (remove in 5.0):
            e_info = dict(engine_uuid=self.ident, engine_id=self.int_id,
                          method='execute')
            reply_content['engine_info'] = e_info


        # Return the execution counter so clients can display prompts
        reply_content['execution_count'] = shell.execution_count - 1

        if 'traceback' in reply_content:
            self.log.info("Exception in execute request:\n%s", '\n'.join(reply_content['traceback']))


        # At this point, we can tell whether the main code execution succeeded
        # or not.  If it did, we proceed to evaluate user_expressions
        if reply_content['status'] == 'ok':
            reply_content[u'user_expressions'] = \
                         shell.user_expressions(user_expressions or {})
        else:
            # If there was an error, don't even try to compute expressions
            reply_content[u'user_expressions'] = {}

        # Payloads should be retrieved regardless of outcome, so we can both
        # recover partial output (that could have been generated early in a
        # block, before an error) and always clear the payload system.
        reply_content[u'payload'] = shell.payload_manager.read_payload()
        # Be aggressive about clearing the payload because we don't want
        # it to sit in memory until the next execute_request comes in.
        shell.payload_manager.clear_payload()

        return reply_content

  