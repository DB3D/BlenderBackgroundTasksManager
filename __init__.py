bl_info = {
    "name": "Multiprocess Demo",
    "author": "Your Name",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Multiprocess",
    "description": "Demonstrates multiprocessing in Blender",
    "category": "Development",
}

#TODO
#-automatically import modules on plugin init and put it on globals.. no more exec(f"import {modulename}", globals()) for every function gathering.. load globals once on plugsess init
#-add op.is_cancelling = True option and op.cancel() which will add a cancel flag to the queue dict

import bpy

import os
import time
import traceback

#simple debug print implementation..
IS_DEBUG = True
def debugprint(*args, **kwargs):
    if (IS_DEBUG):
        print(*args, **kwargs)
    return None

# oooooooooo.  oooo                      oooo         o8o                         
# `888'   `Y8b `888                      `888         `"'                         
#  888     888  888   .ooooo.   .ooooo.   888  oooo  oooo  ooo. .oo.    .oooooooo 
#  888oooo888'  888  d88' `88b d88' `"Y8  888 .8P'   `888  `888P"Y88b  888' `88b  
#  888    `88b  888  888   888 888        888888.     888   888   888  888   888  
#  888    .88P  888  888   888 888   .o8  888 `88b.   888   888   888  `88bod8P'  
# o888bood8P'  o888o `Y8bod8P' `Y8bod8P' o888o o888o o888o o888o o888o `8oooooo.  
#                                                                      d"     YD  
#                                                                      "Y88888P'  
class BlockingQueueProcessingModalMixin:
    """Schedule a series of blocking tasks, with callback to refresh a potential blender interface 
    All tasks will be executed one after the other in a queue manner.
    Use the queue_identifier to specify which queue to use. and define the class.queues map before calling the operator.
    Note that if an error occurs, the whole queue will be cancelled.

    This class is meant to be a mixin subclassed, not to be used directly.
    """

    bl_idname = "*children_defined*"
    bl_label = "*children_defined*"
    bl_description = "*children_defined*"

    queue_identifier : bpy.props.StringProperty(
        default="",
        description="Identifier for the process, in order to retrieve queue instruction for this process in cls.queues",
        )

    # NOTE: about the queues parameter:
    ################### Usage: #############################
    #   change cls.queues dict before calling the operation to add your own tasks!
    #   make sure to set self.queue_identifier and that this value is present in the queue dict.
    ################### Expected format: ###################
    #  <queue_identifier>: {    NOTE: perhaps you wish this class to be able to handle a variety of tasks executions. that is why we need to identigy your queue, will equal to the passed self.queue_identifier
    #     <taskindex>: {       NOTE: The task index, int starting at 0.
    #         'task_pos_args': [<args_value>],                 NOTE: Arguments to pass to the function. self will be pased automatically as first argument!
    #         'task_kw_args': {'<kwarg_name>': <kwarg_value>},       if you'd like to reuse result from a previous task, use notation 'USE_TASK_RESULT|<taskindex>|<result_index>'
    #         'task_fn_blocking': <function>,                  NOTE: Define the blocking function to execute (can have access to bpy). Expect self as first argument! always!
    #         'task_result': <tuple>,                          NOTE: Once the function is finished, we'll catch the result and place it here. the result will always be a tuple!
    #         'task_callback_pre':    <function>,              NOTE: The function to call before or after the task. args are: (self, context, result) for post and (self, context) for pre. Shall return None. 
    #         'task_callback_post':   <function>,
    #     },                    
    #      NOTE: More optional callbacks! signature: (self, context) & return None. 'queue_callback_post' get an additional argument: results_dict, a dict of all the results of the tasks. key is the task index
    #     'queue_callback_pre': <function>,         NOTE: This callback could be used to build tasks via self (self.queues[self.queue_identifier][task_idx][..]) if needed.
    #     'queue_callback_post': <function>,        NOTE: This callback is to be used to handle the queue after it has been successfully executed.
    #     'queue_callback_fatal_error': <function>, NOTE: This callback is to be used to handle fatal errors, errors that would cancel out the whole queue. (if this happens, 'queue_callback_post' will not be called)
    #  },

    queues = {}

    @classmethod
    def define_blocking_queue(cls, queue_identifier:str, queue_data:dict):
        """Add a queue to the class. Meant for public use.
        or define class.queues[queue_identifier] - .. yourself"""

        tasks_count = 0
        for k,v in queue_data.items():
            if (type(k) is int):

                #ensure these values exists
                assert 'task_pos_args' in v, f"ERROR: define_blocking_queue(): 'task_pos_args' is required in queue_data."
                assert 'task_kw_args' in v, f"ERROR: define_blocking_queue(): 'task_kw_args' is required in queue_data."
                assert 'task_fn_blocking' in v, f"ERROR: define_blocking_queue(): 'task_fn_blocking' is required in queue_data."

                #ensure these two values are by default always set to None
                v['task_result'] = None

                tasks_count += 1
                continue

        if (tasks_count == 0):
            raise ValueError(f"ERROR: {cls.__name__}.define_blocking_queue(): No tasks found in queue_data.")

        cls.queues[queue_identifier] = queue_data
        return None

    @classmethod
    def start_blocking_queue(cls, queue_identifier:str):
        """Start a queue of blocking tasks. Will run bpy.ops. Meant for public use.
        or run the according bpy.ops with the according queue identifier"""

        if (queue_identifier not in cls.queues):
            raise ValueError(f"ERROR: {cls.__name__}.start_blocking_queue(): Queue identifier {queue_identifier} not found in queue dict. Make sure to use define_blocking_queue() classmethod function to define a queue first")

        bpy_operator = getattr(bpy.ops, cls.bl_idname)
        assert bpy_operator, f"ERROR: {cls.__name__}.start_blocking_queue(): Operator '{cls.bl_idname}' not found in bpy.ops."
        bpy_operator(queue_identifier=queue_identifier)

        return None

    def initialize_variables(self):
        """Initialize the operator state variables"""

        self._debugname = self.__class__.bl_idname
        self._modal_timer = None #the modal timer item
        self._modal_timercount = 0 #counter to slow down modal execution to give Blender UI time to update
        self._tasks_count = 0 #the number of tasks in the queue, indicated by the number of tasks indexes (starting at 0).
        self._all_successfully_finished = False #flag to check if the queue was successfully finished.

        self.qactive = None #the queue of tasks corresponding to the queue identifier, a dict of tasks of worker functions to be executed
        self.qidx = 0 #the current index of the task that is being executed

        return None

    def resolve_params_notation(self, paramargs):
        """Resolve result references in args/kwargs, when using the 'USE_TASK_RESULT|<taskindex>|<result_index>' notation for a value."""
        
        def resolve_notation(notation):
            """Resolve a single result reference."""
            
            parts = notation.split('|')
            if (len(parts) != 3):
                raise ValueError(f"ERROR: {self._debugname}.resolve_notation(): Invalid reference notation: {notation}")
            
            task_idx = int(parts[1])
            result_idx = int(parts[2])
            if (task_idx not in self.qactive):
                raise ValueError(f"ERROR: {self._debugname}.resolve_notation(): Task index {task_idx} not found in queue: {self.qactive}")
            result = self.qactive[task_idx]['task_result']
            if (result is None):
                raise ValueError(f"ERROR: {self._debugname}.resolve_notation(): Task{task_idx} results are None! Perhaps it's not ready yet, or perhaps this task return None.")
            try:
                value = self.qactive[task_idx]['task_result'][result_idx]
            except Exception as e:
                raise ValueError(f"ERROR: {self._debugname}.resolve_notation(): Invalid result index: {result_idx} for task {task_idx}: {e}")
            return value
        
        match paramargs:
            case list():
                resolved = []
                for value in paramargs:
                    if (isinstance(value, str) and value.startswith('USE_TASK_RESULT|')):
                            resolved.append(resolve_notation(value))
                    else: resolved.append(value)
                return resolved
            
            case dict():
                resolved = {}
                for key, value in paramargs.items():
                    if (isinstance(value, str) and value.startswith('USE_TASK_RESULT|')):
                            resolved[key] = resolve_notation(value)
                    else: resolved[key] = value
                return resolved
            
            case _:
                raise ValueError(f"ERROR: {self._debugname}.resolve_params_notation(): Invalid argument type: {type(paramargs)} for task {self.qidx}")

    def execute(self, context):
        """initiate the queue on execution, the modal will actually handle the task execution.."""

        # Initialize state variables
        self.initialize_variables()

        #make sure the queue identifier is set..
        if (self.queue_identifier not in self.queues):
            print(f"ERROR: {self._debugname}.execute(): Queue identifier {self.queue_identifier} not found in queue dict.")
            self.cleanup(context)
            return {'FINISHED'}
        self.qactive = self.queues[self.queue_identifier]
        self._tasks_count = len([k for k in self.qactive if (type(k) is int)])

        #call the queue_callback_pre function, if exists
        self.exec_callback(context, 'queue_callback_pre')

        debugprint(f"INFO: {self._debugname}.execute(): Starting function queue processing..")

        # Start modal operation to process tasks one by one with UI updates between them
        self._modal_timer = context.window_manager.event_timer_add(0.01, window=context.window)
        context.window_manager.modal_handler_add(self)
        debugprint(f"INFO: {self._debugname}.execute(): Running modal..")
        return {'RUNNING_MODAL'}

    def exec_callback(self, context, callback_identifier=None,):
        """call the callback function for the current task."""

        if (callback_identifier not in {'task_callback_post','task_callback_pre','queue_callback_fatal_error','queue_callback_pre','queue_callback_post',}):
            print(f"ERROR: {self._debugname}.exec_callback(): Invalid callback identifier: {callback_identifier}")
            return None

        #get the callback function, either stored on task or queue level
        if callback_identifier.startswith('task_'):
            callback = self.qactive[self.qidx].get(callback_identifier, None)
        elif callback_identifier.startswith('queue_'):
            callback = self.qactive.get(callback_identifier, None)
        else:
            print(f"ERROR: {self._debugname}.exec_callback(): Invalid callback identifier: {callback_identifier}. Should always start with 'task_' or 'queue_'")
            return None

        if (callback is None):
            return None
        if (not callable(callback)):
            print(f"ERROR: {self._debugname}.exec_callback(): Callback function {callback_identifier} is not callable! Please pass a function!")
            return None
    
        #define callback arguments
        args = (self, context,)
        #the 'task_callback_post', 'queue_callback_post' recieve the results as arguments
        match callback_identifier:
            case 'task_callback_post':
                args += (self.qactive[self.qidx]['task_result'],)
            case 'queue_callback_post':
                result_dict = {k:v['task_result'] for k,v in self.qactive.items() if (type(k) is int)}
                args += (result_dict,)
        try:
            debugprint(f"INFO: {self._debugname}.exec_callback(): Calling Task{self.qidx} '{callback_identifier}' with args: {args}")
            callback(*args)
        except Exception as e:
            print(f"ERROR: {self._debugname}.exec_callback(): Error calling Task{self.qidx} '{callback_identifier}': {e}")

        return None

    def call_blocking_task(self, context) -> bool:
        """Execute the current task directly, in a blocking manner.
        return True if the task was executed successfully, False otherwise."""

        try:
            # call the 'task_callback_pre' function, if exists
            self.exec_callback(context, 'task_callback_pre')

            # get the function..
            taskfunc = self.qactive[self.qidx]['task_fn_blocking']
            if (taskfunc is None):
                print(f"ERROR: {self._debugname}.call_blocking_task(): Function task{self.qidx} was not found!")
                return False

            # get the arguments we need to pass to the function
            args = self.qactive[self.qidx]['task_pos_args']
            kwargs = self.qactive[self.qidx]['task_kw_args']

            # Resolve any result references in args and kwargs
            resolved_args = self.resolve_params_notation(args) if args else []
            resolved_kwargs = self.resolve_params_notation(kwargs) if kwargs else {}

            # Execute the function directly (blocking)
            debugprint(f"INFO: {self._debugname}.call_blocking_task(): Executing Task{self.qidx}...")
            result = taskfunc(self, *resolved_args, **resolved_kwargs)

            # Ensure result is always stored as a tuple for consistent indexing
            if (not isinstance(result, tuple)):
                result = (result,)

            self.qactive[self.qidx]['task_result'] = result

            # call the 'task_callback_post' function, if exists
            self.exec_callback(context, 'task_callback_post')
            
            debugprint(f"INFO: {self._debugname}.call_blocking_task(): Task{self.qidx} finished! Results: {result}")
            return True

        except Exception as e:
            print(f"ERROR: {self._debugname}.call_blocking_task(): Error executing task{self.qidx}: {e}")
            traceback.print_exc()
            return False

    def modal(self, context, event):

        # Check if processing is complete
        if (event.type != 'TIMER'):
            return {'PASS_THROUGH'}

        # Slow down processing to allow UI updates
        # that way blender UI have time to breathe.
        self._modal_timercount += 1
        if (self._modal_timercount != 10):
            return {'RUNNING_MODAL'}
        self._modal_timercount = 0

        # Check if we are at the end of the queue
        if (self.qidx >= self._tasks_count):
            self.successful_finish(context)
            self.cleanup(context)
            return {'FINISHED'}

        # Execute the current task
        succeeded = self.call_blocking_task(context)
        if (not succeeded):
            self.cleanup(context)
            return {'FINISHED'}

        # Move to the next task
        self.qidx += 1
        return {'RUNNING_MODAL'}

    def successful_finish(self, context):
        """finish the queue."""

        self._all_successfully_finished = True

        #debug print the result of each queue tasks?
        global IS_DEBUG
        if (IS_DEBUG):
            print(f"INFO: {self._debugname}.finish(): All tasks finished! Results:")
            for k,v in self.qactive.items():
                if (type(k) is int):
                    print(f"     Task{k}: {v['task_result']}")

        return None
        
    def cleanup(self, context):
        """clean up our operator after use."""

        #callback if something went wrong
        if (not self._all_successfully_finished):
              self.exec_callback(context, 'queue_callback_fatal_error')
        else: self.exec_callback(context, 'queue_callback_post')

        #remove timer
        if (self._modal_timer):
            context.window_manager.event_timer_remove(self._modal_timer)
            self._modal_timer = None

        # reset counters & idx's
        self.qidx = 0
        self._modal_timercount = 0
        self._tasks_count = 0

        debugprint(f"INFO: {self._debugname}.cleanup(): clean up done")
        return None


# ooo        ooooo             oooo      .    o8o  ooooooooo.                                                             o8o                         
# `88.       .888'             `888    .o8    `"'  `888   `Y88.                                                           `"'                         
#  888b     d'888  oooo  oooo   888  .o888oo oooo   888   .d88' oooo d8b  .ooooo.   .ooooo.   .ooooo.   .oooo.o  .oooo.o oooo  ooo. .oo.    .oooooooo 
#  8 Y88. .P  888  `888  `888   888    888   `888   888ooo88P'  `888""8P d88' `88b d88' `"Y8 d88' `88b d88(  "8 d88(  "8 `888  `888P"Y88b  888' `88b  
#  8  `888'   888   888   888   888    888    888   888          888     888   888 888       888ooo888 `"Y88b.  `"Y88b.   888   888   888  888   888  
#  8    Y     888   888   888   888    888 .  888   888          888     888   888 888   .o8 888    .o o.  )88b o.  )88b  888   888   888  `88bod8P'  
# o8o        o888o  `V88V"V8P' o888o   "888" o888o o888o        d888b    `Y8bod8P' `Y8bod8P' `Y8bod8P' 8""888P' 8""888P' o888o o888o o888o `8oooooo.  
#                                                                                                                                          d"     YD  
#                                                                                                                                          "Y88888P'  

import sys
import multiprocessing

#TODO improve this..
BACKGROUND_TASKS_MODULE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backgroundtasks")
assert os.path.exists(BACKGROUND_TASKS_MODULE), f"Background tasks module not found: {BACKGROUND_TASKS_MODULE}"

MULTIPROCESSING_ALLOCATED_CORES = -1
MULTIPROCESSING_POOL = None

def init_multiprocessing(process_alloc=90):
    """start a new multiprocessing pool, used in this plugin."""    
    global MULTIPROCESSING_ALLOCATED_CORES, MULTIPROCESSING_POOL

    # insert a new path to sys.path, so the background tasks module can be found by the 
    # multiprocessing module.. as it will copy the sys.path list to a new process outside of GIL..
    sys.path.insert(0, BACKGROUND_TASKS_MODULE)
    
    #calculate the number of cores to use, and start a new pool.
    MULTIPROCESSING_ALLOCATED_CORES = max(1, int(multiprocessing.cpu_count() * process_alloc/100))
    MULTIPROCESSING_POOL = multiprocessing.get_context('spawn').Pool(MULTIPROCESSING_ALLOCATED_CORES)

    return None

def deinit_multiprocessing():
    """destroy the multiprocessing pool, used in this plugin."""
    global MULTIPROCESSING_ALLOCATED_CORES, MULTIPROCESSING_POOL

    # pool's closed (due to..)
    MULTIPROCESSING_POOL.close()
    MULTIPROCESSING_POOL.join()
    MULTIPROCESSING_POOL = None

    #reset the working cores
    MULTIPROCESSING_ALLOCATED_CORES = -1

    #remove temp module from sys.path
    if (BACKGROUND_TASKS_MODULE in sys.path):
        sys.path.remove(BACKGROUND_TASKS_MODULE)

    return None

#   .oooooo.                                                  
#  d8P'  `Y8b                                                 
# 888      888    oooo  oooo   .ooooo.  oooo  oooo   .ooooo.  
# 888      888    `888  `888  d88' `88b `888  `888  d88' `88b 
# 888      888     888   888  888ooo888  888   888  888ooo888 
# `88b    d88b     888   888  888    .o  888   888  888    .o 
#  `Y8bood8P'Ybd'  `V88V"V8P' `Y8bod8P'  `V88V"V8P' `Y8bod8P'                                                           

class BackgroundQueueProcessingModalMixin:
    """Schedule a series of background tasks using the multiprocessing module (not tied to python GIL).
    All tasks will be executed one after the other in a queue manner.
    Use the queue_identifier to specify which queue to use. and define the class.queues map before calling the operator.
    Note that if an error occurs, the whole queue will be cancelled.

    This class is meant to be a mixin subclassed, not to be used directly.
    """

    bl_idname = "*children_defined*"
    bl_label = "*children_defined*"
    bl_description = "*children_defined*"

    queue_identifier : bpy.props.StringProperty(
        default="",
        description="Identifier for the process, in order to retrieve queue instruction for this process in cls.queues",
        )

    # NOTE: about the queues parameter:
    ################### Usage: #############################
    #   change cls.queues dict before calling the operation to add your own tasks!
    #   make sure to set self.queue_identifier and that this value is present in the queue dict.
    ################### Expected format: ###################
    #  <queue_identifier>: {    NOTE: perhaps you wish to run this operator simultaneously with multiple processes? that is why we need to identigy your queue, will equal to the passed self.queue_identifier
    #     <taskindex>: {       NOTE: The task index, int starting at 0.
    #         'task_modu_name': <myscript.py>,                 NOTE: The script name where your function is located. This module shall be totally independent from blender and make no use of bpy!
    #         'task_pos_args': [<args_value>],                 NOTE: Arguments to pass to the function. These values must be pickeable (bpy independant)!
    #         'task_kw_args': {'<kwarg_name>': <kwarg_value>},       if you'd like to reuse result from a previous task, use notation 'USE_TASK_RESULT|<taskindex>|<result_index>'
    #         'task_fn_name': "<task_fn_name>",                NOTE: The name of the function you wish to execute in background
    #                                                                the function must be pickleable and found on module top level!
    #         'task_fn_worker': <function>,                    NOTE: We'll import and add the function to this emplacement. Just set it to None!
    #         'task_result': <tuple>,                          NOTE: Once the function is finished, we'll catch the result and place it here. the result will always be a tuple!
    #         'task_callback_pre':    <function>,              NOTE: The function to call before or after the task. args are: (self, context, result) for post and (self, context) for pre. Shall return None. 
    #         'task_callback_post':   <function>,                    callbacks will never execute in background, it will be called in the main thread. 
    #     },                                                         therefore it will block blender UI, but give access to bpy, letting you bridge your background process with blender (ex updating an interface).
    #      NOTE: More optional callbacks! signature: (self, context) & return None. 'queue_callback_post' get an additional argument: results_dict, a dict of all the results of the tasks. key is the task index
    #     'queue_callback_pre': <function>,         NOTE: This callback could be used to build tasks via self (self.queues[self.queue_identifier][task_idx][..]) if needed.
    #     'queue_callback_post': <function>,        NOTE: This callback is to be used to handle the queue after it has been successfully executed.
    #     'queue_callback_fatal_error': <function>, NOTE: This callback is to be used to handle fatal errors, errors that would cancel out the whole queue. (if this happens, 'queue_callback_post' will not be called)
    #  },

    queues = {}

    @classmethod
    def define_background_queue(cls, queue_identifier:str, queue_data:dict):
        """Add a queue to the class. Meant for public use.
        or define class.queues[queue_identifier] - .. yourself"""

        tasks_count = 0
        for k,v in queue_data.items():
            if (type(k) is int):

                #ensure these values exists
                assert 'task_modu_name' in v, f"ERROR: define_background_queue(): 'task_modu_name' is required in queue_data."
                assert 'task_pos_args' in v, f"ERROR: define_background_queue(): 'task_pos_args' is required in queue_data."
                assert 'task_kw_args' in v, f"ERROR: define_background_queue(): 'task_kw_args' is required in queue_data."
                assert 'task_fn_name' in v, f"ERROR: define_background_queue(): 'task_fn_name' is required in queue_data."

                #ensure these two values are by default always set to None
                v['task_fn_worker'] = None
                v['task_result'] = None

                tasks_count += 1
                continue

        if (tasks_count == 0):
            raise ValueError(f"ERROR: {cls.__name__}.define_background_queue(): No tasks found in queue_data.")

        cls.queues[queue_identifier] = queue_data
        return None

    @classmethod
    def start_background_queue(cls, queue_identifier:str):
        """Start a queue of background tasks. Will run bpy.ops. Meant for public use.
        or run the according bpy.ops with the according queue identifier"""

        if (queue_identifier not in cls.queues):
            raise ValueError(f"ERROR: {cls.__name__}.start_background_queue(): Queue identifier {queue_identifier} not found in queue dict. Make sure to use define_background_queue() classmethod function to define a queue first")

        bpy_operator = getattr(bpy.ops, cls.bl_idname)
        assert bpy_operator, f"ERROR: {cls.__name__}.start_background_queue(): Operator '{cls.bl_idname}' not found in bpy.ops."
        bpy_operator(queue_identifier=queue_identifier)

        return None

    def initialize_variables(self):
        """Initialize the operator state variables"""

        self._debugname = self.__class__.bl_idname
        self._modal_timer = None #the modal timer item, important for tracking the currently running background task.
        self._pool_result = None #the results currently being awaited for the task being processed. the return value of Pool.map_async()
        self._tasks_count = 0 #the number of tasks in the queue, indicated by the number of tasks indexes (starting at 0).
        self._all_successfully_finished = False #flag to check if the queue was successfully finished.
        
        self.qactive = None #the queue of tasks corresponding to the queue identifier, a dict of tasks of worker functions to be executed
        self.qidx = 0 #the current index of the task that is being executed
        
        return None

    def import_worker_fct(self, modulename, function_name):
        """temporarily add module to sys.path, so it can be found by multiprocessing, 
        clearing our any potential bl_ext dependencies issues"""
        
        # TODO: IMPROVEMENTS:
        # procedurally import all the worker modules on plugin init..
        # Import the standalone worker module
        try:
            modulename = modulename.replace(".py", "")
            exec(f"import {modulename}", globals())
            module_worker = globals()[modulename]
        except Exception as e:
            print(f"ERROR: {self._debugname}.import_worker_fct(): Something went wrong while importing {modulename}: {e}")
            return None

        # Find our function
        function_worker = getattr(module_worker, function_name, None)
        if (not function_worker):
            print(f"ERROR: {self._debugname}.import_worker_fct(): Function {function_name} does not exist in {modulename}. make sure it's found in the first level of this module.")
            return None

        return function_worker

    def collect_worker_fcts(self, context) -> bool:
        """create a queue of functions to be executed. 
        return True if all worker functions were found, False if there was an error otherwise."""

        all_tasks_count = 0
        valid_tasks_found_count = 0

        for k,v in self.qactive.items():
            if (type(k) is int):
                all_tasks_count += 1
                function_worker = self.import_worker_fct(v['task_modu_name'], v['task_fn_name'])
                if callable(function_worker):
                    self.qactive[k]['task_fn_worker'] = function_worker
                    valid_tasks_found_count += 1

        if (all_tasks_count != valid_tasks_found_count):
            print(f"ERROR: {self._debugname}.collect_worker_fcts(): Something went wrong. We couldn't import all the worker functions for your queue.")
            return False

        self._tasks_count = valid_tasks_found_count
        return True

    def resolve_params_notation(self, paramargs):
        """Resolve result references in args/kwargs, when using the 'USE_TASK_RESULT|<taskindex>|<result_index>' notation for a value."""
        
        def resolve_notation(notation):
            """Resolve a single result reference."""
            
            parts = notation.split('|')
            if (len(parts) != 3):
                raise ValueError(f"ERROR: {self._debugname}.resolve_notation(): Invalid reference notation: {notation}")
            
            task_idx = int(parts[1])
            result_idx = int(parts[2])
            if (task_idx not in self.qactive):
                raise ValueError(f"ERROR: {self._debugname}.resolve_notation(): Task index {task_idx} not found in queue: {self.qactive}")
            result = self.qactive[task_idx]['task_result']
            if (result is None):
                raise ValueError(f"ERROR: {self._debugname}.resolve_notation(): Task{task_idx} results are None! Perhaps it's not ready yet, or perhaps this task return None.")
            try:
                value = self.qactive[task_idx]['task_result'][result_idx]
            except Exception as e:
                raise ValueError(f"ERROR: {self._debugname}.resolve_notation(): Invalid result index: {result_idx} for task {task_idx}: {e}")
            return value
        
        match paramargs:
            case list():
                resolved = []
                for value in paramargs:
                    if (isinstance(value, str) and value.startswith('USE_TASK_RESULT|')):
                            resolved.append(resolve_notation(value))
                    else: resolved.append(value)
                return resolved
            
            case dict():
                resolved = {}
                for key, value in paramargs.items():
                    if (isinstance(value, str) and value.startswith('USE_TASK_RESULT|')):
                            resolved[key] = resolve_notation(value)
                    else: resolved[key] = value
                return resolved
            
            case _:
                raise ValueError(f"ERROR: {self._debugname}.resolve_params_notation(): Invalid argument type: {type(paramargs)} for task {self.qidx}")

    def execute(self, context):
        """initiate the queue on execution, the modal will actually handle the task execution.."""

        # Initialize state variables
        self.initialize_variables()

        #make sure the queue identifier is set..
        if (self.queue_identifier not in self.queues):
            print(f"ERROR: {self._debugname}.execute(): Queue identifier {self.queue_identifier} not found in queue dict.")
            self.cleanup(context)
            return {'FINISHED'}
        self.qactive = self.queues[self.queue_identifier]

        #call the queue_callback_pre function, if exists
        self.exec_callback(context, 'queue_callback_pre')

        debugprint(f"INFO: {self._debugname}.execute(): Starting multiprocessing..")
        try:            

            # create the function queue
            succeeded = self.collect_worker_fcts(context)
            if (not succeeded):
                self.cleanup(context)
                return {'FINISHED'}

            # Start modal operation
            self._modal_timer = context.window_manager.event_timer_add(0.15, window=context.window)
            context.window_manager.modal_handler_add(self)
            debugprint(f"INFO: {self._debugname}.execute(): Running modal..")
            return {'RUNNING_MODAL'}

        except Exception as e:
            print(f"ERROR: {self._debugname}.execute(): Error starting multiprocessing: {e}")
            traceback.print_exc()
            self.cleanup(context)
            return {'FINISHED'}

    def exec_callback(self, context, callback_identifier=None,):
        """call the callback function for the current task."""

        if (callback_identifier not in {'task_callback_post','task_callback_pre','queue_callback_fatal_error','queue_callback_pre','queue_callback_post',}):
            print(f"ERROR: {self._debugname}.exec_callback(): Invalid callback identifier: {callback_identifier}")
            return None

        #get the callback function, either stored on task or queue level
        if callback_identifier.startswith('task_'):
            callback = self.qactive[self.qidx].get(callback_identifier, None)
        elif callback_identifier.startswith('queue_'):
            callback = self.qactive.get(callback_identifier, None)
        else:
            print(f"ERROR: {self._debugname}.exec_callback(): Invalid callback identifier: {callback_identifier}. Should always start with 'task_' or 'queue_'")
            return None

        if (callback is None):
            return None
        if (not callable(callback)):
            print(f"ERROR: {self._debugname}.exec_callback(): Callback function {callback_identifier} is not callable! Please pass a function!")
            return None
    
        #define callback arguments
        args = (self, context,)
        #the 'task_callback_post', 'queue_callback_post' recieve the results as arguments
        match callback_identifier:
            case 'task_callback_post':
                args += (self.qactive[self.qidx]['task_result'],)
            case 'queue_callback_post':
                result_dict = {k:v['task_result'] for k,v in self.qactive.items() if (type(k) is int)}
                args += (result_dict,)
        try:
            debugprint(f"INFO: {self._debugname}.exec_callback(): Calling Task{self.qidx} '{callback_identifier}' with args: {args}")
            callback(*args)
        except Exception as e:
            print(f"ERROR: {self._debugname}.exec_callback(): Error calling Task{self.qidx} '{callback_identifier}': {e}")

        return None

    def start_background_task(self, context) -> bool:
        """start a task in the pool.
        return True if the task was started successfully, False otherwise."""

        try:
            # call the 'task_callback_pre' function, if exists
            self.exec_callback(context, 'task_callback_pre')

            # get the function..
            taskfunc = self.qactive[self.qidx]['task_fn_worker']
            if (taskfunc is None):
                print(f"ERROR: {self._debugname}.start_background_task(): Function worker task{self.qidx} was not found!")
                return False

            # get the arguments we need to pass to the function
            args = self.qactive[self.qidx]['task_pos_args']
            kwargs = self.qactive[self.qidx]['task_kw_args']

            # Resolve any result references in args and kwargs
            resolved_args = self.resolve_params_notation(args) if args else []
            resolved_kwargs = self.resolve_params_notation(kwargs) if kwargs else {}

            # Use apply_async instead of map_async - it handles multiple args and kwargs naturally
            self._pool_result = MULTIPROCESSING_POOL.apply_async(taskfunc, resolved_args, resolved_kwargs)
        
            debugprint(f"INFO: {self._debugname}.start_background_task(): Task{self.qidx} started!")
            return True
        
        except Exception as e:
            print(f"ERROR: {self._debugname}.start_background_task(): Error starting background task{self.qidx}: {e}")
            traceback.print_exc()
            return False

    def store_task_result(self, context) -> bool:
        """store the result of the task in the queue.
        return True if the result was stored successfully, False otherwise."""

        try:
            result = self._pool_result.get()

            # Ensure result is always stored as a tuple for consistent indexing
            if (not isinstance(result, tuple)):
                result = (result,)
            
            self.qactive[self.qidx]['task_result'] = result

            debugprint(f"INFO: {self._debugname}.store_task_result(): Task{self.qidx} finished! Results: {result}")
            return True
            
        except Exception as e:
            print(f"ERROR: {self._debugname}.store_task_result(): Error getting multiprocessing results: {e}")
            traceback.print_exc()
            return False

    def modal(self, context, event):

        # Check if processing is complete
        if (event.type!='TIMER'):
            return {'PASS_THROUGH'}

        # print("running")

        # if a queue is empty, it means a task is waiting to be done!
        if (self._pool_result is None):

            # if we are at the end of the queue, we can finish the modal
            if (self.qidx >= self._tasks_count):
                self.successful_finish(context)
                self.cleanup(context)
                return {'FINISHED'}

            # if not, we start a new task
            succeeded = self.start_background_task(context)
            if (not succeeded):
                self.cleanup(context)
                return {'FINISHED'}

            return {'PASS_THROUGH'}

                # do we have a task finished? get the results
        if (self._pool_result.ready()):

            if (not self._pool_result.successful()):
                print(f"ERROR: {self._debugname}.modal(): Task{self.qidx} worker function ran into an Error..")
                try: self._pool_result.get() #this line will cause an exception we use to pass the message in console..
                except Exception as e:
                    print(f"  Error: '{e}'")
                    print(f"  Full Traceback:")
                    print("-"*100)
                    traceback.print_exc()
                    print("-"*100)
                self.cleanup(context)
                return {'FINISHED'}

            succeeded = self.store_task_result(context)
            if (not succeeded):
                self.cleanup(context)
                return {'FINISHED'}

            # handle callback functions if exists..
            self.exec_callback(context, 'task_callback_post')

            # set up environement for the next task
            self.qidx += 1
            self._pool_result = None

            return {'PASS_THROUGH'}

        return {'PASS_THROUGH'}

    def successful_finish(self, context):
        """finish the queue."""

        self._all_successfully_finished = True

        #debug print the result of each queue tasks?
        global IS_DEBUG
        if (IS_DEBUG):
            print(f"INFO: {self._debugname}.finish(): All tasks finished! Results:")
            for k,v in self.qactive.items():
                if (type(k) is int):
                    print(f"     Task{k}: {v['task_result']}")

        return None
        
    def cleanup(self, context):
        """clean up our operator after use."""

        #callback if something went wrong
        if (not self._all_successfully_finished):
              self.exec_callback(context, 'queue_callback_fatal_error')
        else: self.exec_callback(context, 'queue_callback_post')

        #remove timer
        if (self._modal_timer):
            context.window_manager.event_timer_remove(self._modal_timer)
            self._modal_timer = None

        #remove result
        if (self._pool_result):
            self._pool_result = None

        # reset counters & idx's
        self.qidx = 0
        self._tasks_count = 0

        debugprint(f"INFO: {self._debugname}.cleanup(): clean up done")
        return None

# ooooooooo.                                oooo  oooo            oooo  
# `888   `Y88.                              `888  `888            `888  
#  888   .d88'  .oooo.   oooo d8b  .oooo.    888   888   .ooooo.   888  
#  888ooo88P'  `P  )88b  `888""8P `P  )88b   888   888  d88' `88b  888  
#  888          .oP"888   888      .oP"888   888   888  888ooo888  888  
#  888         d8(  888   888     d8(  888   888   888  888    .o  888  
# o888o        `Y888""8o d888b    `Y888""8o o888o o888o `Y8bod8P' o888o 


class ParallelQueueProcessingModalMixin:
    """Schedule a series of background tasks stored run in parallel.
    All tasks will be executed in the background in  parallel (if their results are not co dependent).
    Use the taskpile_identifier to specify which queue to use. and define the class.queues map before calling the operator.
    Note that if an error occurs, the whole queue will be cancelled.

    This class is meant to be a mixin subclassed, not to be used directly.
    """

    bl_idname = "*children_defined*"
    bl_label = "*children_defined*"
    bl_description = "*children_defined*"

    taskpile_identifier : bpy.props.StringProperty(
        default="",
        description="Identifier for the process, in order to retrieve queue instruction for this process in cls.queues",
        )

    # NOTE: about the taskpiles parameter:
    ################### Usage: #############################
    #   change cls.taskpiles dict before calling the operation to add your own tasks!
    #   make sure to set self.taskpile_identifier and that this value is present in the taskpiles dict.
    #   the taskpile is a unordered pile of tasks, the order of the tasks is not important, the dependencies will be resolved automatically.
    ################### Expected format: ###################
    #  <taskpile_identifier>: {    NOTE: perhaps you wish to run this operator simultaneously with multiple processes? that is why we need to identigy your queue, will equal to the passed self.taskpile_identifier
    #     <taskindex>: {       NOTE: The task index, int starting at 0.
    #         'task_modu_name': <myscript.py>,                 NOTE: The script name where your function is located. This module shall be totally independent from blender and make no use of bpy!
    #         'task_pos_args': [<args_value>],                 NOTE: Arguments to pass to the function. These values must be pickeable (bpy independant)!
    #         'task_kw_args': {'<kwarg_name>': <kwarg_value>},       if you'd like to reuse result from a previous task, use notation 'USE_TASK_RESULT|<taskindex>|<result_index>' by doing so, paralellization won't be possible for this task!!!
    #         'task_fn_name': "<task_fn_name>",                NOTE: The name of the function you wish to execute in background
    #                                                                the function must be pickleable and found on module top level!
    #         'task_fn_worker': <function>,                    NOTE: We'll import and add the function to this emplacement. Just set it to None!
    #         'task_result': <tuple>,                          NOTE: Once the function is finished, we'll catch the result and place it here. the result will always be a tuple!
    #         'task_callback_pre':    <function>,              NOTE: The function to call before or after the task. args are: (self, context, result) for post and (self, context) for pre. Shall return None. 
    #         'task_callback_post':   <function>,                    callbacks will never execute in background, it will be called in the main thread. 
    #     },                                                         therefore it will block blender UI, but give access to bpy, letting you bridge your background process with blender (ex updating an interface).
    #      NOTE: More optional callbacks! signature: (self, context) & return None. 'taskspile_callback_post' get an additional argument: results_dict, a dict of all the results of the tasks. key is the task index
    #     'taskspile_callback_pre': <function>,         NOTE: This callback could be used to build tasks via self (self.taskpiles[self.taskpile_identifier][task_idx][..]) if needed.
    #     'taskspile_callback_post': <function>,        NOTE: This callback is to be used to handle the queue after it has been successfully executed.
    #     'taskspile_callback_fatal_error': <function>, NOTE: This callback is to be used to handle fatal errors, errors that would cancel out the whole queue. (if this happens, 'taskspile_callback_post' will not be called)
    #  },

    taskpiles = {}

    @classmethod
    def define_parallel_taskpile(cls, taskpile_identifier:str, taskpile_data:dict):
        """Add a taskpile to the class. Meant for public use.
        or define class.taskpiles[taskpile_identifier] - .. yourself"""

        tasks_count = 0
        for k,v in taskpile_data.items():
            if (type(k) is int):

                #ensure these values exists
                assert 'task_modu_name' in v, f"ERROR: define_parallel_taskpile(): 'task_modu_name' is required in taskpile_data."
                assert 'task_pos_args' in v, f"ERROR: define_parallel_taskpile(): 'task_pos_args' is required in taskpile_data."
                assert 'task_kw_args' in v, f"ERROR: define_parallel_taskpile(): 'task_kw_args' is required in taskpile_data."
                assert 'task_fn_name' in v, f"ERROR: define_parallel_taskpile(): 'task_fn_name' is required in taskpile_data."

                #ensure these two values are by default always set to None
                v['task_fn_worker'] = None
                v['task_result'] = None

                tasks_count += 1
                continue

        if (tasks_count == 0):
            raise ValueError(f"ERROR: {cls.__name__}.define_parallel_taskpile(): No tasks found in taskpile_data.")

        cls.taskpiles[taskpile_identifier] = taskpile_data
        return None

    @classmethod
    def start_parallel_taskpile(cls, taskpile_identifier:str):
        """Start a taskpile of parallel tasks. Will run bpy.ops. Meant for public use.
        or run the according bpy.ops with the according taskpile identifier"""

        if (taskpile_identifier not in cls.taskpiles):
            raise ValueError(f"ERROR: {cls.__name__}.start_parallel_taskpile(): Taskpile identifier {taskpile_identifier} not found in taskpiles dict. Make sure to use define_parallel_taskpile() classmethod function to define a taskpile first")

        bpy_operator = getattr(bpy.ops, cls.bl_idname)
        assert bpy_operator, f"ERROR: {cls.__name__}.start_parallel_taskpile(): Operator '{cls.bl_idname}' not found in bpy.ops."
        bpy_operator(taskpile_identifier=taskpile_identifier)

        return None

    def initialize_variables(self):
        """Initialize the operator state variables"""

        self._debugname = self.__class__.bl_idname
        self._modal_timer = None #the modal timer item, important for tracking the currently running background task.
        self._running_tasks = {} #dict mapping task_idx to their AsyncResult objects
        self._completed_tasks = set() #set of completed task indices
        self._available_tasks = [] #list of task indices ready to start (dependencies met)
        self._dependency_graph = {} #mapping of task dependencies: {task_idx: [depends_on_task_idx, ...]}
        self._tasks_count = 0 #the number of tasks in the queue, indicated by the number of tasks indexes (starting at 0).
        self._all_successfully_finished = False #flag to check if the queue was successfully finished.

        self.pileactive = None #the queue of tasks corresponding to the taskpile_identifier, a dict of tasks of worker functions to be executed
        
        return None

    def import_worker_fct(self, modulename, function_name):
        """temporarily add module to sys.path, so it can be found by multiprocessing, 
        clearing our any potential bl_ext dependencies issues"""
        
        # TODO: IMPROVEMENTS:
        # procedurally import all the worker modules on plugin init..
        # Import the standalone worker module
        try:
            modulename = modulename.replace(".py", "")
            exec(f"import {modulename}", globals())
            module_worker = globals()[modulename]
        except Exception as e:
            print(f"ERROR: {self._debugname}.import_worker_fct(): Something went wrong while importing {modulename}: {e}")
            return None

        # Find our function
        function_worker = getattr(module_worker, function_name, None)
        if (not function_worker):
            print(f"ERROR: {self._debugname}.import_worker_fct(): Function {function_name} does not exist in {modulename}. make sure it's found in the first level of this module.")
            return None

        return function_worker

    def collect_worker_fcts(self, context) -> bool:
        """create a queue of functions to be executed. 
        return True if all worker functions were found, False if there was an error otherwise."""

        all_tasks_count = 0
        valid_tasks_found_count = 0

        for k,v in self.pileactive.items():
            if (type(k) is int):
                all_tasks_count += 1
                function_worker = self.import_worker_fct(v['task_modu_name'], v['task_fn_name'])
                if callable(function_worker):
                    self.pileactive[k]['task_fn_worker'] = function_worker
                    valid_tasks_found_count += 1

        if (all_tasks_count != valid_tasks_found_count):
            print(f"ERROR: {self._debugname}.collect_worker_fcts(): Something went wrong. We couldn't import all the worker functions for your taskpile.")
            return False

        self._tasks_count = valid_tasks_found_count
        return True

    def build_dependency_graph(self):
        """Build dependency graph and determine which tasks can run in parallel"""
        
        self._dependency_graph = {}
        
        # First pass: find all dependencies
        for task_idx, task_data in self.pileactive.items():
            if (type(task_idx) is not int):
                continue
                
            dependencies = set()
            
            # Check task_pos_args for USE_TASK_RESULT references
            args = task_data.get('task_pos_args', [])
            for arg in args:
                if (isinstance(arg, str) and arg.startswith('USE_TASK_RESULT|')):
                    dep_task_idx = int(arg.split('|')[1])
                    dependencies.add(dep_task_idx)
            
            # Check task_kw_args for USE_TASK_RESULT references
            kwargs = task_data.get('task_kw_args', {})
            for value in kwargs.values():
                if (isinstance(value, str) and value.startswith('USE_TASK_RESULT|')):
                    dep_task_idx = int(value.split('|')[1])
                    dependencies.add(dep_task_idx)
            
            self._dependency_graph[task_idx] = list(dependencies)
        
        # Second pass: find tasks with no dependencies (can start immediately)
        self._available_tasks = []
        for task_idx, dependencies in self._dependency_graph.items():
            if (len(dependencies) == 0):
                self._available_tasks.append(task_idx)
        
        debugprint(f"INFO: {self._debugname}.build_dependency_graph(): Dependency graph: {self._dependency_graph}")
        debugprint(f"INFO: {self._debugname}.build_dependency_graph(): Initially available tasks: {self._available_tasks}")
        
        return None

    def resolve_params_notation(self, paramargs):
        """Resolve result references in args/kwargs, when using the 'USE_TASK_RESULT|<taskindex>|<result_index>' notation for a value."""
        
        def resolve_notation(notation):
            """Resolve a single result reference."""
            
            parts = notation.split('|')
            if (len(parts) != 3):
                raise ValueError(f"ERROR: {self._debugname}.resolve_notation(): Invalid reference notation: {notation}")
            
            task_idx = int(parts[1])
            result_idx = int(parts[2])
            if (task_idx not in self.pileactive):
                raise ValueError(f"ERROR: {self._debugname}.resolve_notation(): Task index {task_idx} not found in taskpile: {self.pileactive}")
            result = self.pileactive[task_idx]['task_result']
            if (result is None):
                raise ValueError(f"ERROR: {self._debugname}.resolve_notation(): Task{task_idx} results are None! Perhaps it's not ready yet, or perhaps this task return None.")
            try:
                value = self.pileactive[task_idx]['task_result'][result_idx]
            except Exception as e:
                raise ValueError(f"ERROR: {self._debugname}.resolve_notation(): Invalid result index: {result_idx} for task {task_idx}: {e}")
            return value
        
        match paramargs:
            case list():
                resolved = []
                for value in paramargs:
                    if (isinstance(value, str) and value.startswith('USE_TASK_RESULT|')):
                            resolved.append(resolve_notation(value))
                    else: resolved.append(value)
                return resolved
            
            case dict():
                resolved = {}
                for key, value in paramargs.items():
                    if (isinstance(value, str) and value.startswith('USE_TASK_RESULT|')):
                            resolved[key] = resolve_notation(value)
                    else: resolved[key] = value
                return resolved
            
            case _:
                raise ValueError(f"ERROR: {self._debugname}.resolve_params_notation(): Invalid argument type: {type(paramargs)} for task resolution")

    def execute(self, context):
        """initiate the taskpile on execution, the modal will actually handle the task execution.."""

        # Initialize state variables
        self.initialize_variables()

        #make sure the taskpile identifier is set..
        if (self.taskpile_identifier not in self.taskpiles):
            print(f"ERROR: {self._debugname}.execute(): Taskpile identifier {self.taskpile_identifier} not found in taskpiles dict.")
            self.cleanup(context)
            return {'FINISHED'}
        self.pileactive = self.taskpiles[self.taskpile_identifier]

        #call the taskspile_callback_pre function, if exists
        self.exec_callback(context, 'taskspile_callback_pre')

        debugprint(f"INFO: {self._debugname}.execute(): Starting parallel multiprocessing..")
        try:            

            # create the function queue
            succeeded = self.collect_worker_fcts(context)
            if (not succeeded):
                self.cleanup(context)
                return {'FINISHED'}

            # analyze function dependencies
            self.build_dependency_graph()

            # Start modal operation
            self._modal_timer = context.window_manager.event_timer_add(0.15, window=context.window)
            context.window_manager.modal_handler_add(self)
            debugprint(f"INFO: {self._debugname}.execute(): Running modal..")
            return {'RUNNING_MODAL'}

        except Exception as e:
            print(f"ERROR: {self._debugname}.execute(): Error starting parallel multiprocessing: {e}")
            traceback.print_exc()
            self.cleanup(context)
            return {'FINISHED'}

    def exec_callback(self, context, callback_identifier=None, task_idx=None):
        """call the callback function for the current task or taskpile."""

        if (callback_identifier not in {'task_callback_post','task_callback_pre','taskspile_callback_fatal_error','taskspile_callback_pre','taskspile_callback_post',}):
            print(f"ERROR: {self._debugname}.exec_callback(): Invalid callback identifier: {callback_identifier}")
            return None

        #get the callback function, either stored on task or taskspile level
        if callback_identifier.startswith('task_'):
            if (task_idx is None):
                print(f"ERROR: {self._debugname}.exec_callback(): task_idx is required for task callbacks")
                return None
            callback = self.pileactive[task_idx].get(callback_identifier, None)
        elif callback_identifier.startswith('taskspile_'):
            callback = self.pileactive.get(callback_identifier, None)
        else:
            print(f"ERROR: {self._debugname}.exec_callback(): Invalid callback identifier: {callback_identifier}. Should always start with 'task_' or 'taskspile_'")
            return None

        if (callback is None):
            return None
        if (not callable(callback)):
            print(f"ERROR: {self._debugname}.exec_callback(): Callback function {callback_identifier} is not callable! Please pass a function!")
            return None
    
        #define callback arguments
        args = (self, context,)
        #the 'task_callback_post', 'taskspile_callback_post' recieve the results as arguments
        match callback_identifier:
            case 'task_callback_post':
                args += (self.pileactive[task_idx]['task_result'],)
            case 'taskspile_callback_post':
                result_dict = {k:v['task_result'] for k,v in self.pileactive.items() if (type(k) is int)}
                args += (result_dict,)
        try:
            if task_idx is not None:
                debugprint(f"INFO: {self._debugname}.exec_callback(): Calling Task{task_idx} '{callback_identifier}' with args: {args}")
            else:
                debugprint(f"INFO: {self._debugname}.exec_callback(): Calling '{callback_identifier}' with args: {args}")
            callback(*args)
        except Exception as e:
            if task_idx is not None:
                print(f"ERROR: {self._debugname}.exec_callback(): Error calling Task{task_idx} '{callback_identifier}': {e}")
            else:
                print(f"ERROR: {self._debugname}.exec_callback(): Error calling '{callback_identifier}': {e}")

        return None

    def start_parallel_task(self, context, task_idx) -> bool:
        """start a task in the pool.
        return True if the task was started successfully, False otherwise."""

        try:
            # call the 'task_callback_pre' function, if exists
            self.exec_callback(context, 'task_callback_pre', task_idx)

            # get the function..
            taskfunc = self.pileactive[task_idx]['task_fn_worker']
            if (taskfunc is None):
                print(f"ERROR: {self._debugname}.start_parallel_task(): Function worker task{task_idx} was not found!")
                return False

            # get the arguments we need to pass to the function
            args = self.pileactive[task_idx]['task_pos_args']
            kwargs = self.pileactive[task_idx]['task_kw_args']

            # Resolve any result references in args and kwargs
            resolved_args = self.resolve_params_notation(args) if args else []
            resolved_kwargs = self.resolve_params_notation(kwargs) if kwargs else {}

            # Use apply_async instead of map_async - it handles multiple args and kwargs naturally
            async_result = MULTIPROCESSING_POOL.apply_async(taskfunc, resolved_args, resolved_kwargs)
            self._running_tasks[task_idx] = async_result
        
            debugprint(f"INFO: {self._debugname}.start_parallel_task(): Task{task_idx} started! ({len(self._running_tasks)} tasks running)")
            return True
        
        except Exception as e:
            print(f"ERROR: {self._debugname}.start_parallel_task(): Error starting parallel task{task_idx}: {e}")
            traceback.print_exc()
            return False

    def check_completed_tasks(self, context) -> bool:
        """Check for completed tasks and handle their results.
        Return True if no errors occurred, False otherwise."""
        
        completed_task_indices = []
        
        # Check which tasks are completed
        for task_idx, async_result in self._running_tasks.items():
            if async_result.ready():
                completed_task_indices.append(task_idx)
        
        # Process completed tasks
        for task_idx in completed_task_indices:
            async_result = self._running_tasks[task_idx]
            
            # Check if task was successful
            if (not async_result.successful()):
                print(f"ERROR: {self._debugname}.check_completed_tasks(): Task{task_idx} worker function ran into an Error..")
                try: 
                    async_result.get() #this line will cause an exception we use to pass the message in console..
                except Exception as e:
                    print(f"  Error: '{e}'")
                    print(f"  Full Traceback:")
                    print("-"*100)
                    traceback.print_exc()
                    print("-"*100)
                return False
            
            # Store the result
            try:
                result = async_result.get()

                # Ensure result is always stored as a tuple for consistent indexing
                if (not isinstance(result, tuple)):
                    result = (result,)
                
                self.pileactive[task_idx]['task_result'] = result
                debugprint(f"INFO: {self._debugname}.check_completed_tasks(): Task{task_idx} finished! Results: {result}")
                
                # call the 'task_callback_post' function, if exists
                self.exec_callback(context, 'task_callback_post', task_idx)
                
            except Exception as e:
                print(f"ERROR: {self._debugname}.check_completed_tasks(): Error getting multiprocessing results for task{task_idx}: {e}")
                traceback.print_exc()
                return False
            
            # Mark task as completed and remove from running tasks
            self._completed_tasks.add(task_idx)
            del self._running_tasks[task_idx]
        
        # Update available tasks based on newly completed dependencies
        if completed_task_indices:
            self.update_available_tasks()
        
        return True

    def update_available_tasks(self):
        """Update the list of available tasks based on completed dependencies"""
        
        for task_idx, dependencies in self._dependency_graph.items():

            # Skip tasks that are already completed, running, or available
            if (task_idx in self._completed_tasks or 
                task_idx in self._running_tasks or 
                task_idx in self._available_tasks):
                continue
            
            # Check if all dependencies are completed
            if all(dep_idx in self._completed_tasks for dep_idx in dependencies):
                self._available_tasks.append(task_idx)
                debugprint(f"INFO: {self._debugname}.update_available_tasks(): Task{task_idx} is now available (dependencies completed)")

    def start_new_tasks(self, context) -> bool:
        """Start new tasks if we have capacity and available tasks.
        Return True if no errors occurred, False otherwise."""

        # Start new tasks while we have capacity and available tasks
        while ((len(self._running_tasks) < MULTIPROCESSING_ALLOCATED_CORES) and (len(self._available_tasks) > 0)):
            task_idx = self._available_tasks.pop(0)
            succeeded = self.start_parallel_task(context, task_idx)
            if (not succeeded):
                return False

        return True

    def modal(self, context, event):
        
        # Check if processing is complete
        if (event.type!='TIMER'):
            return {'PASS_THROUGH'}

        # Check for completed tasks and handle results
        succeeded = self.check_completed_tasks(context)
        if (not succeeded):
            self.cleanup(context)
            return {'FINISHED'}

        # Start new tasks if possible
        succeeded = self.start_new_tasks(context)
        if (not succeeded):
            self.cleanup(context)
            return {'FINISHED'}

        # Check if all tasks are completed
        if (len(self._completed_tasks) >= self._tasks_count):
            self.successful_finish(context)
            self.cleanup(context)
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def successful_finish(self, context):
        """finish the taskpile."""

        self._all_successfully_finished = True

        #debug print the result of each taskpile tasks?
        global IS_DEBUG
        if (IS_DEBUG):
            print(f"INFO: {self._debugname}.finish(): All tasks finished! Results:")
            for k,v in self.pileactive.items():
                if (type(k) is int):
                    print(f"     Task{k}: {v['task_result']}")

        return None
        
    def cleanup(self, context):
        """clean up our operator after use."""

        #callback if something went wrong
        if (not self._all_successfully_finished):
              self.exec_callback(context, 'taskspile_callback_fatal_error')
        else: self.exec_callback(context, 'taskspile_callback_post')

        #remove timer
        if (self._modal_timer):
            context.window_manager.event_timer_remove(self._modal_timer)
            self._modal_timer = None

        #clear running tasks
        self._running_tasks.clear()
        self._completed_tasks.clear()
        self._available_tasks.clear()
        self._dependency_graph.clear()

        # reset counters
        self._tasks_count = 0

        debugprint(f"INFO: {self._debugname}.cleanup(): clean up done")
        return None

# ooooo                              oooo          
# `888'                              `888          
#  888  ooo. .oo.  .oo.   oo.ooooo.   888   .ooooo.
#  888  `888P"Y88bP"Y88b   888' `88b  888  d88' `88b
#  888   888   888   888   888   888  888  888ooo888
#  888   888   888   888   888   888  888  888    .
# o888o o888o o888o o888o  888bod8P' o888o `Y8bod8P
#                          888                                                                                                                     
#                         o888o                                                                                                                                                                                                                                                                   
# Implementation Examples..

##############################
### Blocking Queue Example ###

def add_monkey(self, ):
    """Add a monkey (Suzanne) to the scene and return it."""
    bpy.ops.mesh.primitive_monkey_add(size=1.0, enter_editmode=False, align='WORLD')
    monkey = bpy.context.active_object
    time.sleep(1.5)
    return monkey

def resize_monkey(self, monkey, size):
    """Resize the monkey to the specified size."""
    monkey.scale = (size, size, size)
    time.sleep(1.5)
    return None

def offset_monkey(self, monkey, y_offset):
    """Offset the monkey along the Y axis by the specified amount."""
    monkey.location.y += y_offset
    time.sleep(1.5)
    return None

class MULTIPROCESS_OT_myblockingqueue(BlockingQueueProcessingModalMixin, bpy.types.Operator):

    bl_idname = "multiprocess.myblockingqueue"
    bl_label = "Launch Blocking Tasks"
    bl_description = "Launch Blocking Tasks"

    queues = {
        "my_blocking_tasks" : {
            #define queue tasks
            0: {
                'task_pos_args': [],
                'task_kw_args': {},
                'task_fn_blocking': add_monkey,
                'task_result': None,
                'task_callback_pre': lambda self, context: set_progress('ex1',0.33),
                'task_callback_post': lambda self, context, result: update_message('ex1',"add_monkey Done!"),
            },
            1: {
                'task_pos_args': ['USE_TASK_RESULT|0|0',2,], #Use result from task 0, index 0 (monkey..)
                'task_kw_args': {},
                'task_fn_blocking': resize_monkey,
                'task_result': None,
                'task_callback_pre': lambda self, context: set_progress('ex1',0.66),
                'task_callback_post': lambda self, context, result: update_message('ex1',"resize_monkey Done!"),
            },
            2: {
                'task_pos_args': ['USE_TASK_RESULT|0|0',2,],  #Use result from task 0, index 0 (monkey..)
                'task_kw_args': {},
                'task_fn_blocking': offset_monkey,
                'task_result': None,
                'task_callback_pre': lambda self, context: set_progress('ex1',0.99),
                'task_callback_post': lambda self, context, result: update_message('ex1',"offset_monkey Done!"),
            },
            #define queue callbacks
            'queue_callback_pre': lambda self, context: set_progress('ex1',0.1),
            'queue_callback_post': lambda self, context, results: set_progress('ex1',0),
            'queue_callback_fatal_error': lambda self, context: update_message('ex1',"Error Occured..."),
        }
    }

################################
### Background Queue Example ###

class MULTIPROCESS_OT_mybackgroundqueue(BackgroundQueueProcessingModalMixin, bpy.types.Operator):

    bl_idname = "multiprocess.mybackgroundqueue"
    bl_label = "Launch Background Tasks"
    bl_description = "Launch Background Tasks"

    queues = {
        "my_background_tasks" : {
            #define queue tasks
            0: {
                'task_modu_name': "my_standalone_worker.py",
                'task_pos_args': [3,],
                'task_kw_args': {},
                'task_fn_name': "mytask",
                'task_fn_worker': None,
                'task_result': None,
                'task_callback_pre': lambda self, context: print("task_callback_pre..."),
                'task_callback_post': lambda self, context, result: update_message('ex2',"Very Nice!"),
            },
            1: {
                'task_modu_name': "my_standalone_worker.py",
                'task_pos_args': ['USE_TASK_RESULT|0|0',], #Use result from task 0, index 0
                'task_kw_args': {"printhis": "Hello There!"},
                'task_fn_name': "mytask",
                'task_fn_worker': None,
                'task_result': None,
                'task_callback_pre': lambda self, context: print("task_callback_pre..."),
                'task_callback_post': lambda self, context, result: update_message('ex2',"King of the Castle!"),
            },
            2: {
                'task_modu_name': "another_test.py",
                'task_pos_args': ['USE_TASK_RESULT|1|0',],  #Use result from task 1, index 0
                'task_kw_args': {},
                'task_fn_name': "myfoo",
                'task_fn_worker': None,
                'task_result': None,
                'task_callback_pre': lambda self, context: print("task_callback_pre..."),
                'task_callback_post': lambda self, context, result: update_message('ex2',"Done!"),
            },
            #define queue callbacks
            'queue_callback_pre': lambda self, context: print("Callback: Before queue"),
            'queue_callback_post': lambda self, context, results: update_message('ex2',"All Done!"),
            'queue_callback_fatal_error': lambda self, context: update_message('ex2',"Error Occured..."),
        }
    }

###############################
### Parallel Tasks Example ###

class MULTIPROCESS_OT_myparalleltasks(ParallelQueueProcessingModalMixin, bpy.types.Operator):

    bl_idname = "multiprocess.myparalleltasks"
    bl_label = "Launch Parallel Tasks"
    bl_description = "Launch Parallel Tasks with complex dependency tree"

    taskpiles = {
        "my_complex_parallel_tasks" : {
            # Wave 0: 5 independent solo tasks (run in parallel)
            0: {
                'task_modu_name':  "my_parallel_worker.py",
                'task_pos_args': [1, "DataA"],
                'task_kw_args': {"delay": 2.0},
                'task_fn_name': "process_data",
                'task_fn_worker': None,
                'task_result': None,
                'task_callback_pre': lambda self, context: update_parallel_task_status(0, "running"),
                'task_callback_post': lambda self, context, result: update_parallel_task_status(0, "completed"),
            },
            1: {
                'task_modu_name':  "my_parallel_worker.py",
                'task_pos_args': [2, "DataB"],
                'task_kw_args': {"delay": 1.5},
                'task_fn_name': "process_data",
                'task_fn_worker': None,
                'task_result': None,
                'task_callback_pre': lambda self, context: update_parallel_task_status(1, "running"),
                'task_callback_post': lambda self, context, result: update_parallel_task_status(1, "completed"),
            },
            2: {
                'task_modu_name':  "my_parallel_worker.py",
                'task_pos_args': [3, "DataC"],
                'task_kw_args': {"delay": 2.5},
                'task_fn_name': "process_data",
                'task_fn_worker': None,
                'task_result': None,
                'task_callback_pre': lambda self, context: update_parallel_task_status(2, "running"),
                'task_callback_post': lambda self, context, result: update_parallel_task_status(2, "completed"),
            },
            3: {
                'task_modu_name':  "my_parallel_worker.py",
                'task_pos_args': [4, "DataD"],
                'task_kw_args': {"delay": 1.0},
                'task_fn_name': "process_data",
                'task_fn_worker': None,
                'task_result': None,
                'task_callback_pre': lambda self, context: update_parallel_task_status(3, "running"),
                'task_callback_post': lambda self, context, result: update_parallel_task_status(3, "completed"),
            },
            4: {
                'task_modu_name':  "my_parallel_worker.py",
                'task_pos_args': [5, "DataE"],
                'task_kw_args': {"delay": 1.8},
                'task_fn_name': "process_data",
                'task_fn_worker': None,
                'task_result': None,
                'task_callback_pre': lambda self, context: update_parallel_task_status(4, "running"),
                'task_callback_post': lambda self, context, result: update_parallel_task_status(4, "completed"),
            },
            
            # Wave 1: 2 tasks that depend on solo tasks (queue level 1)
            5: {
                'task_modu_name':  "my_parallel_worker.py",
                'task_pos_args': ['USE_TASK_RESULT|0|0', 'USE_TASK_RESULT|1|0'],  # Depends on tasks 0 and 1
                'task_kw_args': {"operation": "combine"},
                'task_fn_name': "combine_results",
                'task_fn_worker': None,
                'task_result': None,
                'task_callback_pre': lambda self, context: update_parallel_task_status(5, "running"),
                'task_callback_post': lambda self, context, result: update_parallel_task_status(5, "completed"),
            },
            6: {
                'task_modu_name':  "my_parallel_worker.py",
                'task_pos_args': ['USE_TASK_RESULT|2|0', 'USE_TASK_RESULT|3|0', 'USE_TASK_RESULT|4|0'],  # Depends on tasks 2, 3, 4
                'task_kw_args': {"operation": "merge"},
                'task_fn_name': "combine_results",
                'task_fn_worker': None,
                'task_result': None,
                'task_callback_pre': lambda self, context: update_parallel_task_status(6, "running"),
                'task_callback_post': lambda self, context, result: update_parallel_task_status(6, "completed"),
            },
            
            # Wave 2: 2 final tasks that depend on the queue results (queue level 2)
            7: {
                'task_modu_name':  "my_parallel_worker.py",
                'task_pos_args': ['USE_TASK_RESULT|5|0', 'USE_TASK_RESULT|6|0'],  # Depends on task 5,6 results
                'task_kw_args': {},
                'task_fn_name': "analyze_data",
                'task_fn_worker': None,
                'task_result': None,
                'task_callback_pre': lambda self, context: update_parallel_task_status(7, "running"),
                'task_callback_post': lambda self, context, result: update_parallel_task_status(7, "completed"),
            },
            
            # Taskpile callbacks
            'taskspile_callback_pre': lambda self, context: init_parallel_task_tracking(),
            'taskspile_callback_post': lambda self, context, results: finalize_parallel_tasks(results),
            'taskspile_callback_fatal_error': lambda self, context: update_message('ex3', "Error Occurred..."),
        }
    }

#################################
####### Rough GUI Example #######

def tag_redraw_all():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return None

MYMESSAGES = {
    'ex1': "Blocking Queue Infos..",
    'ex2': "Background Queue Infos..",
    'ex3': "Parallel Tasks Infos..",
    }
def update_message(identifier, newmessage,):
    MYMESSAGES[identifier] = newmessage
    tag_redraw_all()
    return None

MYPROGRESS = {
    'ex1': 0,
    'ex2': 0,
    'ex3': 0,
    }
def set_progress(identifier, progress):
    MYPROGRESS[identifier] = progress
    tag_redraw_all()
    return None

# Parallel task tracking for wave visualization
PARALLEL_TASK_STATUS = {}  # {task_idx: "pending"|"running"|"completed"|"error"}

def init_parallel_task_tracking():
    """Initialize tracking for all parallel tasks"""
    global PARALLEL_TASK_STATUS
    PARALLEL_TASK_STATUS = {i: "pending" for i in range(9)}  # Tasks 0-8
    update_message('ex3', "Initializing parallel tasks...")
    tag_redraw_all()
    return None

def update_parallel_task_status(task_idx, status):
    """Update status of a specific task"""
    global PARALLEL_TASK_STATUS
    PARALLEL_TASK_STATUS[task_idx] = status
    
    # Count completed tasks
    completed = sum(1 for s in PARALLEL_TASK_STATUS.values() if s == "completed")
    total = len(PARALLEL_TASK_STATUS)
    
    if completed == total:
        update_message('ex3', f"All tasks completed! ({completed}/{total})")
    else:
        running = sum(1 for s in PARALLEL_TASK_STATUS.values() if s == "running")
        update_message('ex3', f"Progress: {completed}/{total} completed, {running} running")
    
    tag_redraw_all()
    return None

def finalize_parallel_tasks(results):
    """Called when all parallel tasks are finished"""
    update_message('ex3', f"All {len(results)} parallel tasks completed successfully!")
    set_progress('ex3', 0)  # Reset progress
    tag_redraw_all()
    return None

def get_task_wave(task_idx):
    """Get the wave number for a task based on its dependencies"""
    wave_mapping = {
        # Wave 0: Independent tasks
        0: 0, 1: 0, 2: 0, 3: 0, 4: 0,
        # Wave 1: Depends on Wave 0
        5: 1, 6: 1,
        # Wave 2: Depends on Wave 1
        7: 2,
    }
    return wave_mapping.get(task_idx, 0)

class MULTIPROCESS_PT_panel(bpy.types.Panel):

    bl_label = "Multiprocess"
    bl_idname = "MULTIPROCESS_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Multiprocess"

    def draw(self, context):
        layout = self.layout
        
        ###########################################
        #Example 1: blocking queue, has access to bpy tho.
        box = layout.box()
        button = box.column()
        button.scale_y = 1.3
        op = button.operator("multiprocess.myblockingqueue", text="Launch Blocking Queue!", icon='PLAY')
        op.queue_identifier = "my_blocking_tasks"
        #
        box.separator(type='LINE')
        if MYPROGRESS['ex1']>0:
            box.progress(text=MYMESSAGES['ex1'], factor=MYPROGRESS['ex1'], type='BAR')
        else:
            box.label(text=MYMESSAGES['ex1'])
            
        ###########################################
        #Example 2: Non blocking background queue, no access to bpy..
        box = layout.box()
        button = box.column()
        button.scale_y = 1.3
        op = button.operator("multiprocess.mybackgroundqueue", text="Launch Background Queue!", icon='PLAY')
        op.queue_identifier = "my_background_tasks"
        #
        box.separator(type='LINE')
        box.label(text=MYMESSAGES['ex2'])
        
        ###########################################
        #Example 3: Parallel tasks with wave visualization
        box = layout.box()
        
        button = box.column()
        button.scale_y = 1.3
        op = button.operator("multiprocess.myparalleltasks", text="Launch Parallel Tasks!", icon='MODIFIER')
        op.taskpile_identifier = "my_complex_parallel_tasks"

        box.separator(type='LINE')

        # Task wave visualization
        if (PARALLEL_TASK_STATUS):
            wave_box = box.box()
            wave_box.label(text="Task Execution Waves:", icon='NETWORK_DRIVE')

            # Create 3 columns for the 3 waves
            split = wave_box.split(factor=0.33)
            
            # Wave 0 column
            col0 = split.column()
            for task_idx in [0, 1, 2, 3, 4]:
                status = PARALLEL_TASK_STATUS.get(task_idx, "pending")
                icon = {'pending': 'PAUSE', 'running': 'PLAY', 'completed': 'CHECKMARK', 'error': 'ERROR'}[status]
                row = col0.row()
                row.label(text=f"Task{task_idx}: {status.title()}", icon=icon)
            
            # Wave 1 column
            col1 = split.column()
            for task_idx in [5, 6]:
                status = PARALLEL_TASK_STATUS.get(task_idx, "pending")
                icon = {'pending': 'PAUSE', 'running': 'PLAY', 'completed': 'CHECKMARK', 'error': 'ERROR'}[status]
                row = col1.row()
                row.label(text=f"Task{task_idx}: {status.title()}", icon=icon)
            
            # Wave 2 column  
            col2 = split.column()
            for task_idx in [7,]:
                status = PARALLEL_TASK_STATUS.get(task_idx, "pending")
                icon = {'pending': 'PAUSE', 'running': 'PLAY', 'completed': 'CHECKMARK', 'error': 'ERROR'}[status]
                row = col2.row()
                row.label(text=f"Task{task_idx}: {status.title()}", icon=icon)
        
            box.separator(type='LINE')

        # Status message
        box.label(text=MYMESSAGES['ex3'])

        return None

classes = [
    MULTIPROCESS_OT_myblockingqueue,
    MULTIPROCESS_OT_mybackgroundqueue,
    MULTIPROCESS_OT_myparalleltasks,
    MULTIPROCESS_PT_panel,
    ]

def register():

    #create a new multiprocessing pool with 90% of the available cores
    init_multiprocessing(process_alloc=90)

    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    deinit_multiprocessing()
