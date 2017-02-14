''' DataFlow Kernel.

Track dependencies, and execute runnable tasks as dependencies resolve.
'''
import copy
import uuid
from functools import partial
from parsl.dataflow.error import *
import logging
from concurrent.futures import Future
from parsl.dataflow.futures import AppFuture
# Exceptions

logger = logging.getLogger(__name__)

class DataFlowKernel(object):
    """ Manage futures, Data futures etc...

    User             |        DFK         |    Executor
    ----------------------------------------------------------
                     |                    |
          Task-------+> +Submit           |
        App_Fu<------+--|                 |
                     |  Dependencies met  |
                     |         task-------+--> +Submit
                     |        Ex_Fu<------+----|
    """

    def __init__(self, executor):
        """ Initialize
        """
        self.pending         = {}
        self.fut_task_lookup = {}
        self.runnable        = {}
        self.done            = {}
        self.executor        = executor

    @staticmethod
    def _count_deps(depends):
        ''' Count the number of unresolved futures in the list depends'''
        count = 0
        for dep in depends:
            if isinstance(dep, Future) or issubclass(type(dep), Future):
                if not dep.done():
                    count += 1

        logger.debug("Counted deps : {0} on {1}".format(count, depends))
        return count


    def launch_task(self, executable, task_id):
        ''' Handle the actual submission of the task to the executor layer

        We should most likely add a callback at this point
        '''
        logger.debug("Submitting to executor : %s", task_id)
        return self.executor.submit(executable)

    def submit (self, executable, depends, callback):
        ''' Add task to the dataflow system.

        If all deps are met :
              send to the runnable queue
              and launch the task
        Else:
              post the task in the pending queue

        Returns:
               (AppFuture) [DataFutures,]
        '''
        dep_cnt  = self._count_deps(depends)
        task_id  = uuid.uuid4()
        task_def = { 'depends'    : depends,
                     'executable' : executable,
                     'callback'   : callback,
                     'dep_cnt'    : dep_cnt,
                     'exec_fu'    : None,
                     'app_fu'     : None  }

        if dep_cnt == 0 :
            # Send to runnable queue
            if task_id in self.runnable:
                raise DuplicateTaskError("Task {0} in pending list".format(task_id))

            else:
                self.runnable[task_id] = task_def

            task_def['exec_fu']    = self.launch_task(executable, task_id)
            task_def['app_fu']     = AppFuture(task_def['exec_fu'])
            self.runnable[task_id] = task_def

        else:
            # Send to pending queue
            if task_id in self.pending:
                raise DuplicateTaskError("Task {0} in pending list".format(task_id))

            else:
                task_def['app_fu'] = AppFuture(None)
                self.pending[task_id] = task_def


        for fut in depends:
            if fut not in self.fut_task_lookup:
                self.fut_task_lookup[fut] = []
                self.fut_task_lookup[fut].extend([task_id])


        return task_def['app_fu']


    def check_fulfilled(self):
        ''' Iterate over the pending tasks
        For tasks with dep_cnt == 0, copy task to runnable, and make the callback
        '''
        runnable = []
        for task in self.pending:
            if self.pending[task]['dep_cnt'] == 0:
                print("All deps resolved for : ", task, self.pending[task])
                self.runnable[task] = copy.deepcopy ( self.pending[task] )

                runnable.extend([task])

                print("Running callback {0}".format(task))
                self.runnable[task]['callback']

        for task in runnable:
            del self.pending[task]
        return

    def future_resolved(self, fut):
        if fut not in self.fut_task_lookup:
            print("fut not in fut_task_lookup")
            raise MissingFutError("Missing task:{0} in fut_task_lookup".format(fut))
        else:
            for task_id in self.fut_task_lookup.get(fut, None):
                print("Found : ", task_id)
                print("Dep table : ", self.pending[task_id])
                self.pending[task_id]['dep_cnt'] -= 1

    def current_state(self):
        print("Pending :")
        for item in self.pending:
            print("Task{0:5} : DepCnt:{1} | Deps:{2}".format(item, self.pending[item]['dep_cnt'],
                                                             self.pending[item]['depends']))
        print("Lookup  :")
        for item in self.fut_task_lookup:
            print("{0:10} : {1}".format(item, self.fut_task_lookup[item]))



def cbk_fun(*args):
    print("Callback ", *args)


def increment(number):
    return number + 1

def test_linear(N):
    dfk = DFlowKernel()

    dfk.add_task(0, [], partial(increment, 1))
    for item in range(1, N):
        dfk.add_task(item, [item-1], partial(increment, item))

    print("*"*40, "\nCurrent State , b fulfilled")
    dfk.current_state()

    dfk.future_resolved(0)

def simple_tests():
    dfk = DFlowKernel()
    dfk.add_task(1, ['a', 'b'], partial(cbk_fun, 1, ['a', 'b']) )
    dfk.current_state()
    dfk.add_task(2, ['a', 'b'], partial(cbk_fun, 2, ['a', 'b', 'v']) )
    print("*"*40, "\nCurrent State")
    dfk.current_state()

    print("*"*40)
    dfk.future_resolved('a')

    print("*"*40, "\nCurrent State")
    dfk.current_state()
    dfk.check_fulfilled()


    dfk.future_resolved('b')
    print("*"*40, "\nCurrent State , b fulfilled")
    dfk.current_state()
    dfk.check_fulfilled()


    print("*"*40, "\nCurrent State , END")
    dfk.current_state()

if __name__ == '__main__' :

    test_linear(3)
    #simple_tests()