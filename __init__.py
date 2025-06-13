bl_info = {
    "name": "Multiprocess Demo",
    "author": "Your Name",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Multiprocess",
    "description": "Demonstrates multiprocessing in Blender",
    "category": "Development",
}

import bpy

import os
import time
import traceback

# 888888 88   88 88b 88  dP""b8 .dP"Y8 
# 88__   88   88 88Yb88 dP   `" `Ybo." 
# 88""   Y8   8P 88 Y88 Yb      o.`Y8b 
# 88     `YbodP' 88  Y8  YboodP 8bodP' 
# Useful utils functions

IS_DEBUG = True
def debugprint(*args, **kwargs):
    """simple debug prints implementations"""
    if (IS_DEBUG):
        print(*args, **kwargs)
    return None

def is_modal_active(modal_class):
    """return a list of modal operators bl_idname currently running"""
    #collect a list of cls__name__ modals running (bl_idname api is false here..)
    all_running_modals = [op.bl_idname for w in bpy.context.window_manager.windows for op in w.modal_operators]
    return modal_class.__name__ in all_running_modals

# .dP"Y8 88  88    db    88""Yb 888888 8888b.  
# `Ybo." 88  88   dPYb   88__dP 88__    8I  Yb 
# o.`Y8b 888888  dP__Yb  88"Yb  88""    8I  dY 
# 8bodP' 88  88 dP""""Yb 88  Yb 888888 8888Y"  
# Function made for all 3 Queue classes

def resolve_params_notation(self, parameters:tuple|list|dict,) -> tuple|list|dict:
    """Resolve result references in args/kwargs, when using the 'USE_TASK_RESULT|<taskindex>|<result_index>' notation for a value."""
    
    assert hasattr(self, 'q_active'), f"ERROR: resolve_params_notation(): 'q_active' not found in self. (self={self})"
    assert hasattr(self, '_debugname'), f"ERROR: resolve_params_notation(): 'q_task_idx' not found in self. (self={self})"
    
    def resolve_notation(notation):
        """Resolve a single result reference."""

        parts = notation.split('|')
        if (len(parts) != 3):
            raise ValueError(f"ERROR: resolve_notation({self._debugname}): Invalid reference notation: '{notation}'. Should follow the format 'USE_TASK_RESULT|<taskindex>|<result_index>'")
        
        task_id = int(parts[1])
        result_idx = int(parts[2])
        if (task_id not in self.q_active):
            raise ValueError(f"ERROR: resolve_notation({self._debugname}): Task index {task_id} not found in queue: {self.q_active}")
        result = self.q_active[task_id]['task_result']
        if (result is None):
            raise ValueError(f"ERROR: resolve_notation({self._debugname}): Task{task_id} results are None! Perhaps it's not ready yet, or perhaps this task return None.")
        try:
            value = self.q_active[task_id]['task_result'][result_idx]
        except Exception as e:
            raise ValueError(f"ERROR: resolve_notation({self._debugname}): Invalid result index: {result_idx} for task {task_id}: {e}")
        return value
    
    match parameters:

        case list()|tuple():
            resolved = []
            for value in parameters:
                if (isinstance(value, str) and value.startswith('USE_TASK_RESULT|')):
                        resolved.append(resolve_notation(value))
                else: resolved.append(value)
            return resolved
        
        case dict():
            resolved = {}
            for key, value in parameters.items():
                if (isinstance(value, str) and value.startswith('USE_TASK_RESULT|')):
                        resolved[key] = resolve_notation(value)
                else: resolved[key] = value
            return resolved
        
        case _:
            raise ValueError(f"ERROR: resolve_params_notation({self._debugname}): Invalid argument type: {type(parameters)} for task {self.q_task_idx if hasattr(self,'q_task_idx') else 'unknown'}")

def call_callback(self, context, callback_identifier:str=None, task_id:int=None) -> None:
    """call the callback function of the class active queue/queue based on the given identifiers"""

    assert hasattr(self, 'q_active'), f"ERROR: resolve_params_notation(): 'q_active' not found in self. (self={self})"
    assert hasattr(self, '_debugname'), f"ERROR: resolve_params_notation(): 'q_task_idx' not found in self. (self={self})"

    # make sure the callbacks are valid..
    if (callback_identifier not in {
            'task_callback_post',
            'task_callback_pre',
            'queue_callback_pre',
            'queue_callback_modal',
            'queue_callback_post',
            'queue_callback_cancel',
            'queue_callback_fatalerror',
            }
        ):
        print(f"ERROR: {self._debugname}.call_callback(): Invalid callback identifier: {callback_identifier}")
        return None
    is_queue_callback, is_task_callback = callback_identifier.startswith('queue_'), callback_identifier.startswith('task_')
    if (not (is_queue_callback or is_task_callback)):
        print(f"ERROR: {self._debugname}.call_callback(): Invalid callback identifier: {callback_identifier}. Should always start with 'queue_' or 'task_'")
        return None
    if (is_task_callback and (task_id is None)):
        print(f"ERROR: {self._debugname}.call_callback(): keyword arg 'task_id' is mandatory for task callbacks.")
        return None

    # get the callback function queue level or callback task level.
    if (is_queue_callback):
        callback = self.q_active.get(callback_identifier, None)
    if (is_task_callback):
        callback = self.q_active[task_id].get(callback_identifier, None)
    # was the callback found?
    if (callback is None):
        return None
    # if it was found, is it a callable? maybe fct user did bs..
    if (not callable(callback)):
        print(f"ERROR: {self._debugname}.call_callback(): Callback function {callback_identifier} is not callable! Please pass a function!")
        return None

    #define callback arguments
    args = (self, context,)
    #the 'task_callback_post', 'queue_callback_post' recieve additional results arguments
    match callback_identifier:
        case 'task_callback_post':
            args += (self.q_active[task_id]['task_result'],)
        case 'queue_callback_post':
            result_dict = {k:v['task_result'] for k,v in self.q_active.items() if (type(k) is int)}
            args += (result_dict,)

    # call the callback
    try:
        if (is_task_callback):
              debugprint(f"INFO: {self._debugname}.call_callback(): Calling Task{task_id} callback '{callback_identifier}'")
        else: debugprint(f"INFO: {self._debugname}.call_callback(): Calling queue callback '{callback_identifier}'")
        callback(*args)

    # error during call?
    except Exception as e:
        if (is_task_callback):
              print(f"ERROR: {self._debugname}.call_callback(): Error calling Task{task_id} callback '{callback_identifier}'. Error message:\n{e}")
        else: print(f"ERROR: {self._debugname}.call_callback(): Error calling queue callback '{callback_identifier}'. Error message:\n{e}")

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

    bl_idname = "chidren.defined"
    bl_label = "ChildrenDefined"
    bl_description = "ChildrenDefined"

    queue_identifier : bpy.props.StringProperty(
        default="",
        description="Identifier for the process, in order to retrieve queue instruction for this process in cls.queues",
        options={'SKIP_SAVE'},
        )
    send_cancel_request : bpy.props.BoolProperty(
        default=False,
        description="Cancel the modal potentially running at the given 'queue_identifier'",
        options={'SKIP_SAVE'},
        )

    # NOTE: about the queues parameter:
    ################### Usage: #############################
    #   change cls.queues dict before calling the operation to add your own tasks!
    #   make sure to set self.queue_identifier and that this value is present in the queue dict.
    ################### Expected format: ###################
    #  <queue_identifier:str>: { NOTE: perhaps you wish this class to be able to handle a variety of tasks executions. that is why we need to identigy your queue, will equal to the passed self.queue_identifier
    #     <taskindex:int>: {<taskindex:int>: {     NOTE: The task index, int starting at 0.
    #         'task_pos_args': [<args_value>],                 NOTE: Arguments to pass to the function. self will be pased automatically as first argument!
    #         'task_kw_args': {'<kwarg_name>': <kwarg_value>},       if you'd like to reuse result from a previous task, use notation 'USE_TASK_RESULT|<taskindex>|<result_index>'
    #         'task_fn_blocking': <function>,                  NOTE: Define the blocking function to execute (can have access to bpy). Expect self as first argument! always!
    #         'task_result': <tuple:private>,                  NOTE: Once the function is finished, we'll catch the result and place it here. the result will always be a tuple!
    #         'task_callback_pre': <function>,                 NOTE: The function to call before or after the task. args are: (self, context, result) for post and (self, context) for pre. Shall return None. 
    #         'task_callback_post': <function>,  
    #     },                    
    #      NOTE: More optional callbacks! signature: (self, context) & return None. 'queue_callback_post' get an additional argument: results_dict, a dict of all the results of the tasks. key is the task index
    #     'queue_callback_pre': <function>,         NOTE: This callback could be used to build tasks via self (self.queues[self.queue_identifier][taskindex][..]) if needed.
    #     'queue_callback_post': <function>,        NOTE: This callback is to be used to handle the queue after it has been successfully executed.
    #     'queue_callback_modal': <function>,       NOTE: This callback is called every modal timer event.
    #     'queue_callback_cancel': <function>,      NOTE: This callback is to be used to handle manual user cancellation.
    #     'queue_callback_fatalerror': <function>,  NOTE: This callback is to be used to handle fatal errors, errors that would cancel out the whole queue. (if this happens, 'queue_callback_post' will not be called)
    #  },

    queues = {}
    runningidentifiers = [] #list of <queue_identifier:str> currently being ran. #NOTE currently unused, blocking ops don't support multiple instances running..
    cancelrequests = [] #list of <queue_identifier:str> being asked to be cancelled.

    @classmethod
    def is_running(cls, queue_identifier:str) -> bool:
        """check if a queue is currently running"""
        # NOTE: the blocking queue operator don't support running multiple ..
        return is_modal_active(cls)

    def initialize_variables(self):
        """Initialize the operator state variables"""

        self._debugname = self.__class__.bl_idname
        self._modal_timer = None #the modal timer item
        self._modal_timercount = 0 #counter to slow down modal execution to give Blender UI time to update
        self._tasks_count = 0 #the number of tasks in the queue, indicated by the number of tasks indexes (starting at 0).
        self._allfinished = False #flag to check if the queue was successfully finished.

        self.q_active = None #the queue of tasks corresponding to the queue identifier, a dict of tasks of worker functions to be executed
        self.q_task_idx = 0 #the current index of the task that is being executed

        return None

    def execute(self, context):
        """initiate the queue on execution, the modal will actually handle the task execution.."""
        cls = self.__class__

        # Are we simply sending a cancel request signal to the class??
        if (self.send_cancel_request==True):
            if (self.queue_identifier in cls.runningidentifiers) and (self.queue_identifier not in cls.cancelrequests):
                cls.cancelrequests.append(self.queue_identifier)
            return {'FINISHED'}
        
        # Check if we are able to run another instance of this class..
        if cls.is_running(self.queue_identifier):
            print(f"WARNING: modal operator '{self.__name__}' of identifier '{self.queue_identifier}' is already running!")
            return None
        cls.runningidentifiers.append(self.queue_identifier) # define a new running identifier. In order to is_running() to work properly..

        # Initialize state variables
        self.initialize_variables()

        #make sure the queue identifier is set..
        if (self.queue_identifier not in self.queues):
            print(f"ERROR: {self._debugname}.execute(): Queue identifier {self.queue_identifier} not found in queue dict.")
            self.cleanup(context)
            return {'FINISHED'}
        self.q_active = self.queues[self.queue_identifier]
        self._tasks_count = len([k for k in self.q_active if (type(k) is int)])

        #call the queue_callback_pre function, if exists
        call_callback(self, context, callback_identifier='queue_callback_pre',)

        debugprint(f"INFO: {self._debugname}.execute(): Starting function queue processing..")

        # Start modal operation to process tasks one by one with UI updates between them
        self._modal_timer = context.window_manager.event_timer_add(0.01, window=context.window)
        context.window_manager.modal_handler_add(self)
        debugprint(f"INFO: {self._debugname}.execute(): Running modal..")
        return {'RUNNING_MODAL'}

    def call_blocking_task(self, context) -> bool:
        """Execute the current task directly, in a blocking manner.
        return True if the task was executed successfully, False otherwise."""

        try:
            # call the 'task_callback_pre' function, if exists
            call_callback(self, context, callback_identifier='task_callback_pre', task_id=self.q_task_idx,)

            # get the function..
            taskfunc = self.q_active[self.q_task_idx]['task_fn_blocking']
            if (taskfunc is None):
                print(f"ERROR: {self._debugname}.call_blocking_task(): Function task{self.q_task_idx} was not found!")
                return False

            # get the arguments we need to pass to the function
            args = self.q_active[self.q_task_idx]['task_pos_args']
            kwargs = self.q_active[self.q_task_idx]['task_kw_args']

            # Resolve any result references in args and kwargs
            resolved_args = resolve_params_notation(self,args) if args else []
            resolved_kwargs = resolve_params_notation(self,kwargs) if kwargs else {}

            # Execute the function directly (blocking)
            debugprint(f"INFO: {self._debugname}.call_blocking_task(): Executing Task{self.q_task_idx}...")
            result = taskfunc(self, *resolved_args, **resolved_kwargs)

            # Ensure result is always stored as a tuple for consistent indexing
            if (not isinstance(result, tuple)):
                result = (result,)

            self.q_active[self.q_task_idx]['task_result'] = result

            # call the 'task_callback_post' function, if exists
            call_callback(self, context, callback_identifier='task_callback_post', task_id=self.q_task_idx,)
            
            debugprint(f"INFO: {self._debugname}.call_blocking_task(): Task{self.q_task_idx} finished! Results: {result}")
            return True

        except Exception as e:
            print(f"ERROR: {self._debugname}.call_blocking_task(): Error executing task{self.q_task_idx}: {e}")
            traceback.print_exc()
            return False

    def modal(self, context, event):
        cls = self.__class__

        # Check there is a cancel request
        is_cancel_request = bool(self.queue_identifier in cls.cancelrequests)
        if (is_cancel_request):
            self.cleanup(context)
            return {'FINISHED'}

        # Check if processing is complete
        if (event.type != 'TIMER'):
            return {'PASS_THROUGH'}

        # call the 'queue_callback_modal' function, if exists
        call_callback(self, context, callback_identifier='queue_callback_modal',)

        # Slow down processing to allow UI updates
        # that way blender UI have time to breathe.
        self._modal_timercount += 1
        if (self._modal_timercount != 10):
            return {'RUNNING_MODAL'}
        self._modal_timercount = 0

        # Check if we are at the end of the queue
        if (self.q_task_idx >= self._tasks_count):
            self.queue_sucessful(context)
            self.cleanup(context)
            return {'FINISHED'}

        # Execute the current task
        succeeded = self.call_blocking_task(context)
        if (not succeeded):
            self.cleanup(context)
            return {'FINISHED'}

        # Move to the next task
        self.q_task_idx += 1
        return {'RUNNING_MODAL'}

    def queue_sucessful(self, context):
        """finish the queue."""

        self._allfinished = True

        #debug print the result of each queue tasks?
        global IS_DEBUG
        if (IS_DEBUG):
            print(f"INFO: {self._debugname}.finish(): All tasks finished! Results:")
            for k,v in self.q_active.items():
                if (type(k) is int):
                    print(f"     Task{k}: {v['task_result']}")

        return None
        
    def cleanup(self, context):
        """clean up our operator after use."""
        cls = self.__class__

        # finishing callbacks
        is_cancel_request = bool(self.queue_identifier in cls.cancelrequests)
        if (is_cancel_request):
            call_callback(self, context, callback_identifier='queue_callback_cancel',)
        elif (not self._allfinished):
            call_callback(self, context, callback_identifier='queue_callback_fatalerror',)
        else:
            call_callback(self, context, callback_identifier='queue_callback_post',)

        #remove timer
        if (self._modal_timer):
            context.window_manager.event_timer_remove(self._modal_timer)
            self._modal_timer = None
        
        #remove cancel request
        if (is_cancel_request):
            cls.cancelrequests.remove(self.queue_identifier)

        # reset counters & idx's
        self.q_task_idx = 0
        self._modal_timercount = 0
        self._tasks_count = 0

        # the queue is no longer running
        if (self.queue_identifier in cls.runningidentifiers):
            cls.runningidentifiers.remove(self.queue_identifier)

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
# Here we handle the set up of our multiprocessing pool, and we store our independent worker elements                                      "Y88888P'  

import sys
import importlib
import multiprocessing

WORKER_MODULES = {}
WORKER_MODULES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backgroundtasks")

MULTIPROCESSING_ALLOCATED_CORES = -1
MULTIPROCESSING_POOL = None

def multiproc_set_worker_items():
    """store all the modules meant to be used as a background task in one dict.
    We do that once for all our independent modules and functions made for multiprocessing.
    That way we don't constantly import all functions call on runtime, just on plugin init."""

    global WORKER_MODULES
    for dirpath, dirnames, filenames in os.walk(WORKER_MODULES_FOLDER):
        for filename in filenames:
            if (filename.endswith('.py')):
                modulename = filename.replace(".py", "")

                # We procedurally import that module
                try:
                    importline = f"import {modulename}"
                    catch = {}
                    exec(importline, catch)
                    module = catch[modulename]
                except Exception as e:
                    print(f"ERROR: register.multiproc_init.multiproc_set_worker_items(): Something went wrong while importing {modulename}: {e}")
                    return None

                # Find all the top-level functions from that module
                module_functions = {}
                for name, obj in vars(module).items():
                    if callable(obj) and not name.startswith('_'):
                        module_functions[name] = obj

                # We store that module and it's independent functions 
                if (len(module_functions)==0):
                    print(f"WARNING: register.multiproc_init.multiproc_set_worker_items(): No functions found in module '{filename}'")
                    continue
                WORKER_MODULES[filename] = {"module": module, "functions": module_functions,}
                debugprint(f"INFO: register.multiproc_init.multiproc_set_worker_items(): Found functions {list(module_functions.keys())} in module '{filename}'")

                continue

    return None

def multiproc_get_worker_fct(module_path, function_name):
    """temporarily add module to sys.path, so it can be found by multiprocessing, 
    clearing our any potential bl_ext dependencies issues"""

    # Get our independent module
    worker_itm = WORKER_MODULES.get(module_path)
    if (not worker_itm):
        print(f"ERROR: multiproc_get_worker_fct(): Module '{module_path}' not found. An error must've happened earlier at plugin register during multiproc_set_worker_items().")
        return None

    # Find our independent worker function
    function_worker = worker_itm['functions'].get(function_name, None)
    if (not function_worker):
        print(f"ERROR: multiproc_get_worker_fct(): Function '{function_name}' does not exist in '{module_path}'. make sure it's found in the first level of this module.")
        return None
    # safety check..
    if (not callable(function_worker)):
        print(f"ERROR: multiproc_get_worker_fct(): Function '{function_name}' in '{module_path}' is not a function...")
        return None

    return function_worker

def multiproc_init(process_alloc=90):
    """start a new multiprocessing pool, used in this plugin."""

    # insert a new path to sys.path, so the background tasks module can be found by the 
    # multiprocessing module.. as it will copy the sys.path list to a new process outside of GIL..
    global WORKER_MODULES_FOLDER
    if (not os.path.exists(WORKER_MODULES_FOLDER)):
        print(f"ERROR: register.multiproc_init(): Background tasks folder not found, multiprocessing couldn't initiate.. Expect errors..: {WORKER_MODULES_FOLDER}")
        return None
    sys.path.insert(0, WORKER_MODULES_FOLDER)
    
    # calculate the number of cores to use
    global MULTIPROCESSING_ALLOCATED_CORES
    MULTIPROCESSING_ALLOCATED_CORES = max(1, int(multiprocessing.cpu_count() * process_alloc/100))
    
    # and start a new pool.
    global MULTIPROCESSING_POOL
    MULTIPROCESSING_POOL = multiprocessing.get_context('spawn').Pool(MULTIPROCESSING_ALLOCATED_CORES)

    # store all the modules in the background tasks
    multiproc_set_worker_items()

    return None

def multiproc_deinit():
    """destroy the multiprocessing pool, used in this plugin."""

    # pool's closed (due to..)
    global MULTIPROCESSING_POOL
    MULTIPROCESSING_POOL.close()
    MULTIPROCESSING_POOL.join()
    MULTIPROCESSING_POOL = None

    # reset the working cores
    global MULTIPROCESSING_ALLOCATED_CORES
    MULTIPROCESSING_ALLOCATED_CORES = -1

    # remove temp module from sys.path
    global WORKER_MODULES_FOLDER
    if (WORKER_MODULES_FOLDER in sys.path):
        sys.path.remove(WORKER_MODULES_FOLDER)
    
    # remove the worker items
    global WORKER_MODULES
    WORKER_MODULES = {}

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

    bl_idname = "chidren.defined"
    bl_label = "ChildrenDefined"
    bl_description = "ChildrenDefined"

    queue_identifier : bpy.props.StringProperty(
        default="",
        description="Identifier for the process, in order to retrieve queue instruction for this process in cls.queues",
        options={'SKIP_SAVE'},
        )
    send_cancel_request : bpy.props.BoolProperty(
        default=False,
        description="Cancel the modal potentially running at the given 'queue_identifier'",
        options={'SKIP_SAVE'},
        )

    # NOTE: about the queues parameter:
    ################### Usage: #############################
    #   change cls.queues dict before calling the operation to add your own tasks!
    #   make sure to set self.queue_identifier and that this value is present in the queue dict.
    ################### Expected format: ###################
    #  <queue_identifier:str>: { NOTE: perhaps you wish to run this operator simultaneously with multiple processes? that is why we need to identigy your queue, will equal to the passed self.queue_identifier
    #     <taskindex:int>: {     NOTE: The task index, int starting at 0.
    #         'task_modu_name': <myscript.py>,                 NOTE: The script name where your function is located. This module shall be totally independent from blender and make no use of bpy!
    #         'task_pos_args': [<args_value>],                 NOTE: Arguments to pass to the function. These values must be pickeable (bpy independant)!
    #         'task_kw_args': {'<kwarg_name>': <kwarg_value>},       if you'd like to reuse result from a previous task, use notation 'USE_TASK_RESULT|<taskindex>|<result_index>'
    #         'task_fn_name': "<task_fn_name>",                NOTE: The name of the function you wish to execute in background
    #                                                                the function must be pickleable and found on module top level!
    #         'task_fn_worker': <function:private>,            NOTE: We'll import and add the function to this emplacement. Just set it to None!
    #         'task_result': <tuple:private>,                  NOTE: Once the function is finished, we'll catch the result and place it here. the result will always be a tuple!
    #         'task_callback_pre': <function>,                 NOTE: The function to call before or after the task. args are: (self, context, result) for post and (self, context) for pre. Shall return None. 
    #         'task_callback_post': <function>,                      callbacks will never execute in background, it will be called in the main thread. 
    #     },                                                         therefore it will block blender UI, but give access to bpy, letting you bridge your background process with blender (ex updating an interface).
    #      NOTE: More optional callbacks! signature: (self, context) & return None. 'queue_callback_post' get an additional argument: results_dict, a dict of all the results of the tasks. key is the task index
    #     'queue_callback_pre': <function>,         NOTE: This callback could be used to build tasks via self (self.queues[self.queue_identifier][taskindex][..]) if needed.
    #     'queue_callback_post': <function>,        NOTE: This callback is to be used to handle the queue after it has been successfully executed.
    #     'queue_callback_modal': <function>,       NOTE: This callback is called every modal timer event.
    #     'queue_callback_cancel': <function>,      NOTE: This callback is to be used to handle manual user cancellation.
    #     'queue_callback_fatalerror': <function>,  NOTE: This callback is to be used to handle fatal errors, errors that would cancel out the whole queue. (if this happens, 'queue_callback_post' will not be called)
    #  },

    queues = {}
    runningidentifiers = [] #list of <queue_identifier:str> currently being ran.
    cancelrequests = [] #list of <queue_identifier:str> being asked to be cancelled.

    @classmethod
    def is_running(cls, queue_identifier:str) -> bool:
        """check if a queue is currently running"""
        if (not is_modal_active(cls)):
            return False
        if (queue_identifier not in cls.queues):
            debugprint(f"WARNING:' {queue_identifier}' not found in {cls.__name__}.queues")
            return False
        return (queue_identifier in cls.runningidentifiers)

    def initialize_variables(self):
        """Initialize the operator state variables"""

        self._debugname = self.__class__.bl_idname
        self._modal_timer = None #the modal timer item, important for tracking the currently running background task.
        self._async_result = None #the results currently being awaited for the task being processed. the return value of Pool.map_async()
        self._tasks_count = 0 #the number of tasks in the queue, indicated by the number of tasks indexes (starting at 0).
        self._allfinished = False #flag to check if the queue was successfully finished.

        self.q_active = None #the queue of tasks corresponding to the queue identifier, a dict of tasks of worker functions to be executed
        self.q_task_idx = 0 #the current index of the task that is being executed

        return None

    def collect_background_tasks(self, context) -> bool:
        """collect all independent functions to be executed and place them back into the queue. 
        return True if all worker functions were found, False if there was an error otherwise."""

        all_tasks_count = 0
        valid_tasks_count = 0

        for k,v in self.q_active.items():
            if (type(k) is int):
                all_tasks_count += 1
                function_worker = multiproc_get_worker_fct(v['task_modu_name'], v['task_fn_name'])
                if (function_worker):
                    self.q_active[k]['task_fn_worker'] = function_worker
                    valid_tasks_count += 1

        if (all_tasks_count != valid_tasks_count):
            print(f"ERROR: {self._debugname}.collect_background_tasks(): Something went wrong. We couldn't import all the worker functions for your queue.")
            return False

        self._tasks_count = valid_tasks_count
        return True

    def execute(self, context):
        """initiate the queue on execution, the modal will actually handle the task execution.."""
        cls = self.__class__

        # Are we simply sending a cancel request signal to the class??
        if (self.send_cancel_request==True):
            if (self.queue_identifier in cls.runningidentifiers) and (self.queue_identifier not in cls.cancelrequests):
                cls.cancelrequests.append(self.queue_identifier)
            return {'FINISHED'}

        # Check if we are able to run another instance of this class..
        if cls.is_running(self.queue_identifier):
            print(f"WARNING: modal operator '{self.__name__}' of identifier '{self.queue_identifier}' is already running!")
            return None
        cls.runningidentifiers.append(self.queue_identifier) # define a new running identifier. In order to is_running() to work properly..

        # Initialize state variables
        self.initialize_variables()

        #make sure the queue identifier is set..
        if (self.queue_identifier not in self.queues):
            print(f"ERROR: {self._debugname}.execute(): Queue identifier {self.queue_identifier} not found in queue dict.")
            self.cleanup(context)
            return {'FINISHED'}
        self.q_active = self.queues[self.queue_identifier]

        #call the queue_callback_pre function, if exists
        call_callback(self, context, callback_identifier='queue_callback_pre',)

        debugprint(f"INFO: {self._debugname}.execute(): Starting multiprocessing..")
        try:            

            # create the function queue
            succeeded = self.collect_background_tasks(context)
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

    def start_background_task(self, context) -> bool:
        """start a task in the pool.
        return True if the task was started successfully, False otherwise."""

        try:
            # call the 'task_callback_pre' function, if exists
            call_callback(self, context, callback_identifier='task_callback_pre', task_id=self.q_task_idx,)

            # get the function..
            taskfunc = self.q_active[self.q_task_idx]['task_fn_worker']
            if (taskfunc is None):
                print(f"ERROR: {self._debugname}.start_background_task(): Function worker task{self.q_task_idx} was not found!")
                return False

            # get the arguments we need to pass to the function
            args = self.q_active[self.q_task_idx]['task_pos_args']
            kwargs = self.q_active[self.q_task_idx]['task_kw_args']

            # Resolve any result references in args and kwargs
            resolved_args = resolve_params_notation(self,args) if args else []
            resolved_kwargs = resolve_params_notation(self,kwargs) if kwargs else {}

            # Use apply_async instead of map_async - it handles multiple args and kwargs naturally
            self._async_result = MULTIPROCESSING_POOL.apply_async(taskfunc, resolved_args, resolved_kwargs)

            debugprint(f"INFO: {self._debugname}.start_background_task(): Task{self.q_task_idx} started!")
            return True

        except Exception as e:
            print(f"ERROR: {self._debugname}.start_background_task(): Error starting background task{self.q_task_idx}: {e}")
            traceback.print_exc()
            return False

    def store_background_task_result(self, context) -> bool:
        """store the result of the task in the queue.
        return True if the result was stored successfully, False otherwise."""

        try:
            result = self._async_result.get()

            # Ensure result is always stored as a tuple for consistent indexing
            if (not isinstance(result, tuple)):
                result = (result,)
            
            self.q_active[self.q_task_idx]['task_result'] = result

            debugprint(f"INFO: {self._debugname}.store_background_task_result(): Task{self.q_task_idx} finished! Results: {result}")
            return True
            
        except Exception as e:
            print(f"ERROR: {self._debugname}.store_background_task_result(): Error getting multiprocessing results: {e}")
            traceback.print_exc()
            return False

    def modal(self, context, event):
        cls = self.__class__

        # Check there is a cancel request
        is_cancel_request = bool(self.queue_identifier in cls.cancelrequests)
        if (is_cancel_request):
            self.cleanup(context)
            return {'FINISHED'}

        # Check if processing is complete
        if (event.type!='TIMER'):
            return {'PASS_THROUGH'}

        # call the 'queue_callback_modal' function, if exists
        call_callback(self, context, callback_identifier='queue_callback_modal',)

        # if a queue is empty, it means a task is waiting to be done!
        if (self._async_result is None):

            # if we are at the end of the queue, we can finish the modal
            if (self.q_task_idx >= self._tasks_count):
                self.queue_sucessful(context)
                self.cleanup(context)
                return {'FINISHED'}

            # if not, we start a new task
            succeeded = self.start_background_task(context)
            if (not succeeded):
                self.cleanup(context)
                return {'FINISHED'}

            return {'PASS_THROUGH'}

                # do we have a task finished? get the results
        if (self._async_result.ready()):

            if (not self._async_result.successful()):
                print(f"ERROR: {self._debugname}.modal(): Task{self.q_task_idx} worker function ran into an Error..")
                try: self._async_result.get() #this line will cause an exception we use to pass the message in console..
                except Exception as e:
                    print(f"  Error: '{e}'")
                    print(f"  Full Traceback:")
                    print("-"*100)
                    traceback.print_exc()
                    print("-"*100)
                self.cleanup(context)
                return {'FINISHED'}

            succeeded = self.store_background_task_result(context)
            if (not succeeded):
                self.cleanup(context)
                return {'FINISHED'}

            # handle callback functions if exists..
            call_callback(self, context, callback_identifier='task_callback_post', task_id=self.q_task_idx,)

            # set up environement for the next task
            self.q_task_idx += 1
            self._async_result = None

            return {'PASS_THROUGH'}

        return {'PASS_THROUGH'}

    def queue_sucessful(self, context):
        """finish the queue."""

        self._allfinished = True

        #debug print the result of each queue tasks?
        global IS_DEBUG
        if (IS_DEBUG):
            print(f"INFO: {self._debugname}.finish(): All tasks finished! Results:")
            for k,v in self.q_active.items():
                if (type(k) is int):
                    print(f"     Task{k}: {v['task_result']}")

        return None
        
    def cleanup(self, context):
        """clean up our operator after use."""
        cls = self.__class__

        # finishing callbacks
        is_cancel_request = bool(self.queue_identifier in cls.cancelrequests)
        if (is_cancel_request):
            call_callback(self, context, callback_identifier='queue_callback_cancel',)
        elif (not self._allfinished):
            call_callback(self, context, callback_identifier='queue_callback_fatalerror',)
        else:
            call_callback(self, context, callback_identifier='queue_callback_post',)

        #remove timer
        if (self._modal_timer):
            context.window_manager.event_timer_remove(self._modal_timer)
            self._modal_timer = None

        #remove cancel request
        if (is_cancel_request):
            cls.cancelrequests.remove(self.queue_identifier)

        #remove result
        if (self._async_result):
            self._async_result = None

        # reset counters & idx's
        self.q_task_idx = 0
        self._tasks_count = 0
        
        # the queue is no longer running
        if (self.queue_identifier in cls.runningidentifiers):
            cls.runningidentifiers.remove(self.queue_identifier)

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
    Use the queue_identifier to specify which queue to use. and define the class.queues map before calling the operator.
    Note that if an error occurs, the whole queue will be cancelled.

    This class is meant to be a mixin subclassed, not to be used directly.
    """

    bl_idname = "chidren.defined"
    bl_label = "ChildrenDefined"
    bl_description = "ChildrenDefined"

    queue_identifier : bpy.props.StringProperty(
        default="",
        description="Identifier for the process, in order to retrieve queue instruction for this process in cls.queues",
        options={'SKIP_SAVE'},
        )
    send_cancel_request : bpy.props.BoolProperty(
        default=False,
        description="Cancel the modal potentially running at the given 'queue_identifier'",
        options={'SKIP_SAVE'},
        )

    # NOTE: about the queues parameter:
    ################### Usage: #############################
    #   change cls.queues dict before calling the operation to add your own tasks!
    #   make sure to set self.queue_identifier and that this value is present in the queues dict.
    #   the queue, in this context, is a unordered pile of tasks, the order of the tasks is not important, the dependencies will be resolved automatically.
    ################### Expected format: ###################
    #  <queue_identifier:str>: { NOTE: perhaps you wish to run this operator simultaneously with multiple processes? that is why we need to identigy your queue, will equal to the passed self.queue_identifier
    #     <taskid:int>: {        NOTE: The task index, int starting at 0.
    #         'task_modu_name': <myscript.py>,                 NOTE: The script name where your function is located. This module shall be totally independent from blender and make no use of bpy!
    #         'task_pos_args': [<args_value>],                 NOTE: Arguments to pass to the function. These values must be pickeable (bpy independant)!
    #         'task_kw_args': {'<kwarg_name>': <kwarg_value>},       if you'd like to reuse result from a previous task, use notation 'USE_TASK_RESULT|<taskindex>|<result_index>' by doing so, paralellization won't be possible for this task!!!
    #         'task_fn_name': "<task_fn_name>",                NOTE: The name of the function you wish to execute in background
    #                                                                the function must be pickleable and found on module top level!
    #         'task_fn_worker': <function:private>,            NOTE: We'll import and add the function to this emplacement. Just set it to None!
    #         'task_result': <tuple:private>,                  NOTE: Once the function is finished, we'll catch the result and place it here. the result will always be a tuple!
    #         'task_callback_pre': <function>,                 NOTE: The function to call before or after the task. args are: (self, context, result) for post and (self, context) for pre. Shall return None. 
    #         'task_callback_post': <function>,                      callbacks will never execute in background, it will be called in the main thread. 
    #     },                                                         therefore it will block blender UI, but give access to bpy, letting you bridge your background process with blender (ex updating an interface).
    #      NOTE: More optional callbacks! signature: (self, context) & return None. 'queue_callback_post' get an additional argument: results_dict, a dict of all the results of the tasks. key is the task index
    #     'queue_callback_pre': <function>,         NOTE: This callback could be used to build tasks via self (self.queues[self.queue_identifier][taskid][..]) if needed.
    #     'queue_callback_post': <function>,        NOTE: This callback is to be used to handle the queue after it has been successfully executed.
    #     'queue_callback_modal': <function>,       NOTE: This callback is called every modal timer event.
    #     'queue_callback_cancel': <function>,      NOTE: This callback is to be used to handle manual user cancellation.
    #     'queue_callback_fatalerror': <function>,  NOTE: This callback is to be used to handle fatal errors, errors that would cancel out the whole queue. (if this happens, 'queue_callback_post' will not be called)
    #  },

    queues = {}
    runningidentifiers = [] #list of <queues> currently being ran.
    cancelrequests = [] #list of <queues> being asked to be cancelled.

    @classmethod
    def is_running(cls, queue_identifier:str) -> bool:
        """check if a queue is currently running"""
        if (not is_modal_active(cls)):
            return False
        if (queue_identifier not in cls.queues):
            debugprint(f"WARNING:' {queue_identifier}' not found in {cls.__name__}.queues")
            return False
        return (queue_identifier in cls.runningidentifiers)

    def initialize_variables(self):
        """Initialize the operator state variables"""

        self._debugname = self.__class__.bl_idname
        self._modal_timer = None #the modal timer item, important for tracking the currently running background task.
        self._running_tasks = {} #dict mapping task_id to their AsyncResult objects
        self._completed_tasks = set() #set of completed task indices
        self._available_tasks = [] #list of task indices ready to start (dependencies met)
        self._dependency_graph = {} #mapping of task dependencies: {task_id: [depends_on_task_id, ...]}
        self._tasks_count = 0 #the number of tasks in the queue, indicated by the number of tasks indexes (starting at 0).
        self._allfinished = False #flag to check if the queue was successfully finished.

        self.q_active = None #the queue of tasks corresponding to the queue_identifier, a dict of tasks of worker functions to be executed
        
        return None

    def collect_parallel_tasks(self, context) -> bool:
        """collect all independent functions to be executed and place them back into the queue. 
        return True if all worker functions were found, False if there was an error otherwise."""

        all_tasks_count = 0
        valid_tasks_count = 0

        for k,v in self.q_active.items():
            if (type(k) is int):
                all_tasks_count += 1
                function_worker = multiproc_get_worker_fct(v['task_modu_name'], v['task_fn_name'])
                if (function_worker):
                    self.q_active[k]['task_fn_worker'] = function_worker
                    valid_tasks_count += 1

        if (all_tasks_count != valid_tasks_count):
            print(f"ERROR: {self._debugname}.collect_parallel_tasks(): Something went wrong. We couldn't import all the worker functions for your queue.")
            return False

        self._tasks_count = valid_tasks_count
        return True

    def build_dependency_graph(self):
        """Build dependency graph and determine which tasks can run in parallel"""
        
        self._dependency_graph = {}
        
        # First pass: find all dependencies
        for task_id, task_data in self.q_active.items():
            if (type(task_id) is not int):
                continue
                
            dependencies = set()
            
            # Check task_pos_args for USE_TASK_RESULT references
            args = task_data.get('task_pos_args', [])
            for arg in args:
                if (isinstance(arg, str) and arg.startswith('USE_TASK_RESULT|')):
                    dep_task_id = int(arg.split('|')[1])
                    dependencies.add(dep_task_id)
            
            # Check task_kw_args for USE_TASK_RESULT references
            kwargs = task_data.get('task_kw_args', {})
            for value in kwargs.values():
                if (isinstance(value, str) and value.startswith('USE_TASK_RESULT|')):
                    dep_task_id = int(value.split('|')[1])
                    dependencies.add(dep_task_id)
            
            self._dependency_graph[task_id] = list(dependencies)
        
        # Second pass: find tasks with no dependencies (can start immediately)
        self._available_tasks = []
        for task_id, dependencies in self._dependency_graph.items():
            if (len(dependencies) == 0):
                self._available_tasks.append(task_id)
        
        debugprint(f"INFO: {self._debugname}.build_dependency_graph(): Dependency graph: {self._dependency_graph}")
        debugprint(f"INFO: {self._debugname}.build_dependency_graph(): Initially available tasks: {self._available_tasks}")
        
        return None

    def execute(self, context):
        """initiate the queue on execution, the modal will actually handle the task execution.."""
        cls = self.__class__

        # Are we simply sending a cancel request signal to the class??
        if (self.send_cancel_request==True):
            if (self.queue_identifier in cls.runningidentifiers) and (self.queue_identifier not in cls.cancelrequests):
                cls.cancelrequests.append(self.queue_identifier)
            return {'FINISHED'}

        # Check if we are able to run another instance of this class..
        if cls.is_running(self.queue_identifier):
            print(f"WARNING: modal operator '{self.__name__}' of identifier '{self.queue_identifier}' is already running!")
            return None
        cls.runningidentifiers.append(self.queue_identifier) # define a new running identifier. In order to is_running() to work properly..

        # Initialize state variables
        self.initialize_variables()

        #make sure the queue identifier is set..
        if (self.queue_identifier not in self.queues):
            print(f"ERROR: {self._debugname}.execute(): Queue identifier {self.queue_identifier} not found in queues dict.")
            self.cleanup(context)
            return {'FINISHED'}
        self.q_active = self.queues[self.queue_identifier]

        #call the queue_callback_pre function, if exists
        call_callback(self, context, callback_identifier='queue_callback_pre',)

        debugprint(f"INFO: {self._debugname}.execute(): Starting parallel multiprocessing..")
        try:            

            # create the function queue
            succeeded = self.collect_parallel_tasks(context)
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

    def start_parallel_task(self, context, task_id) -> bool:
        """start a task in the pool.
        return True if the task was started successfully, False otherwise."""

        try:
            # call the 'task_callback_pre' function, if exists
            call_callback(self, context, callback_identifier='task_callback_pre', task_id=task_id,)

            # get the function..
            taskfunc = self.q_active[task_id]['task_fn_worker']
            if (taskfunc is None):
                print(f"ERROR: {self._debugname}.start_parallel_task(): Function worker task{task_id} was not found!")
                return False

            # get the arguments we need to pass to the function
            args = self.q_active[task_id]['task_pos_args']
            kwargs = self.q_active[task_id]['task_kw_args']

            # Resolve any result references in args and kwargs
            resolved_args = resolve_params_notation(self,args) if args else []
            resolved_kwargs = resolve_params_notation(self,kwargs) if kwargs else {}

            # Use apply_async instead of map_async - it handles multiple args and kwargs naturally
            async_result = MULTIPROCESSING_POOL.apply_async(taskfunc, resolved_args, resolved_kwargs)
            self._running_tasks[task_id] = async_result
        
            debugprint(f"INFO: {self._debugname}.start_parallel_task(): Task{task_id} started! ({len(self._running_tasks)} tasks running)")
            return True
        
        except Exception as e:
            print(f"ERROR: {self._debugname}.start_parallel_task(): Error starting parallel task{task_id}: {e}")
            traceback.print_exc()
            return False

    def check_completed_tasks(self, context) -> bool:
        """Check for completed tasks and handle their results.
        Return True if no errors occurred, False otherwise."""
        
        completed_task_indices = []
        
        # Check which tasks are completed
        for task_id, async_result in self._running_tasks.items():
            if async_result.ready():
                completed_task_indices.append(task_id)
        
        # Process completed tasks
        for task_id in completed_task_indices:
            async_result = self._running_tasks[task_id]
            
            # Check if task was successful
            if (not async_result.successful()):
                print(f"ERROR: {self._debugname}.check_completed_tasks(): Task{task_id} worker function ran into an Error..")
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
                
                self.q_active[task_id]['task_result'] = result
                debugprint(f"INFO: {self._debugname}.check_completed_tasks(): Task{task_id} finished! Results: {result}")
                
                # call the 'task_callback_post' function, if exists
                call_callback(self, context, callback_identifier='task_callback_post', task_id=task_id,)
                
            except Exception as e:
                print(f"ERROR: {self._debugname}.check_completed_tasks(): Error getting multiprocessing results for task{task_id}: {e}")
                traceback.print_exc()
                return False
            
            # Mark task as completed and remove from running tasks
            self._completed_tasks.add(task_id)
            del self._running_tasks[task_id]
        
        # Update available tasks based on newly completed dependencies
        if completed_task_indices:
            self.update_available_tasks()
        
        return True

    def update_available_tasks(self):
        """Update the list of available tasks based on completed dependencies"""
        
        for task_id, dependencies in self._dependency_graph.items():

            # Skip tasks that are already completed, running, or available
            if (task_id in self._completed_tasks or 
                task_id in self._running_tasks or 
                task_id in self._available_tasks):
                continue
            
            # Check if all dependencies are completed
            if all(dep_idx in self._completed_tasks for dep_idx in dependencies):
                self._available_tasks.append(task_id)
                debugprint(f"INFO: {self._debugname}.update_available_tasks(): Task{task_id} is now available (dependencies completed)")

    def start_new_parallel_tasks(self, context) -> bool:
        """Start new tasks if we have capacity and available tasks.
        Return True if no errors occurred, False otherwise."""

        # Start new tasks while we have capacity and available tasks
        while ((len(self._running_tasks) < MULTIPROCESSING_ALLOCATED_CORES) and (len(self._available_tasks) > 0)):
            task_id = self._available_tasks.pop(0)
            succeeded = self.start_parallel_task(context, task_id)
            if (not succeeded):
                return False

        return True

    def modal(self, context, event):
        cls = self.__class__

        # Check there is a cancel request
        is_cancel_request = bool(self.queue_identifier in cls.cancelrequests)
        if (is_cancel_request):
            self.cleanup(context)
            return {'FINISHED'}
    
        # Check if processing is complete
        if (event.type!='TIMER'):
            return {'PASS_THROUGH'}

        # call the 'queue_callback_modal' function, if exists
        call_callback(self, context, callback_identifier='queue_callback_modal',)

        # Check for completed tasks and handle results
        succeeded = self.check_completed_tasks(context)
        if (not succeeded):
            self.cleanup(context)
            return {'FINISHED'}

        # Start new tasks if possible
        succeeded = self.start_new_parallel_tasks(context)
        if (not succeeded):
            self.cleanup(context)
            return {'FINISHED'}

        # Check if all tasks are completed
        if (len(self._completed_tasks) >= self._tasks_count):
            self.queue_sucessful(context)
            self.cleanup(context)
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def queue_sucessful(self, context):
        """finish the queue."""

        self._allfinished = True

        #debug print the result of each queue tasks?
        global IS_DEBUG
        if (IS_DEBUG):
            print(f"INFO: {self._debugname}.finish(): All tasks finished! Results:")
            for k,v in self.q_active.items():
                if (type(k) is int):
                    print(f"     Task{k}: {v['task_result']}")

        return None
        
    def cleanup(self, context):
        """clean up our operator after use."""
        cls = self.__class__

        # finishing callbacks
        is_cancel_request = bool(self.queue_identifier in cls.cancelrequests)
        if (is_cancel_request):
            call_callback(self, context, callback_identifier='queue_callback_cancel',)
        elif (not self._allfinished):
            call_callback(self, context, callback_identifier='queue_callback_fatalerror',)
        else:
            call_callback(self, context, callback_identifier='queue_callback_post',)

        #remove timer
        if (self._modal_timer):
            context.window_manager.event_timer_remove(self._modal_timer)
            self._modal_timer = None

        #remove cancel request
        if (is_cancel_request):
            cls.cancelrequests.remove(self.queue_identifier)

        #clear running tasks
        self._running_tasks.clear()
        self._completed_tasks.clear()
        self._available_tasks.clear()
        self._dependency_graph.clear()

        # reset counters
        self._tasks_count = 0
    
        # the queue is no longer running
        if (self.queue_identifier in cls.runningidentifiers):
            cls.runningidentifiers.remove(self.queue_identifier)

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

def rotate_monkey(self, monkey, y_offset):
    """Offset the monkey along the Y axis by the specified amount."""
    monkey.rotation_euler.y += y_offset
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
                'task_callback_pre': lambda self, context: set_progress('ex1',0.33),
                'task_callback_post': lambda self, context, result: update_message('ex1',"add_monkey Done!"),
            },
            1: {
                'task_pos_args': ['USE_TASK_RESULT|0|0',2,], #Use result from task 0, index 0 (monkey..)
                'task_kw_args': {},
                'task_fn_blocking': resize_monkey,
                'task_callback_pre': lambda self, context: set_progress('ex1',0.66),
                'task_callback_post': lambda self, context, result: update_message('ex1',"resize_monkey Done!"),
            },
            2: {
                'task_pos_args': ['USE_TASK_RESULT|0|0',2,],  #Use result from task 0, index 0 (monkey..)
                'task_kw_args': {},
                'task_fn_blocking': rotate_monkey,
                'task_callback_pre': lambda self, context: set_progress('ex1',669),
                'task_callback_post': lambda self, context, result: update_message('ex1',"rotate_monkey Done!"),
            },
            #define queue callbacks
            'queue_callback_pre': lambda self, context: [set_progress('ex1',0.1), update_message('ex1',"Startin'")],
            'queue_callback_post': lambda self, context, results: [set_progress('ex1',0), update_message('ex1',"All Done!")],
            'queue_callback_cancel': lambda self, context: [set_progress('ex1',0), update_message('ex1',"Cancelled")],
            'queue_callback_fatalerror': lambda self, context: [set_progress('ex1',0), update_message('ex1',"Error Occured...")],
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
                'task_callback_pre': lambda self, context: update_message('ex2',"Starting.."),
                'task_callback_post': lambda self, context, result: update_message('ex2',"Very Nice!"),
            },
            1: {
                'task_modu_name': "my_standalone_worker.py",
                'task_pos_args': ['USE_TASK_RESULT|0|0',], #Use result from task 0, result[0]
                'task_kw_args': {"printhis": "Hello There!"},
                'task_fn_name': "mytask",
                'task_callback_pre': lambda self, context: update_message('ex2',"King of?"),
                'task_callback_post': lambda self, context, result: update_message('ex2',"King of the Castle!"),
            },
            2: {
                'task_modu_name': "another_test.py",
                'task_pos_args': ['USE_TASK_RESULT|1|0',],  #Use result from task 1, result[0]
                'task_kw_args': {},
                'task_fn_name': "myfoo",
                'task_callback_pre': lambda self, context: update_message('ex2',"Almost there.."),
                'task_callback_post': lambda self, context, result: update_message('ex2',"Done!"),
            },
            #define queue callbacks
            'queue_callback_pre': lambda self, context: update_message('ex2',"Start Q!"),
            'queue_callback_post': lambda self, context, results: update_message('ex2',"All Done!"),
            'queue_callback_cancel': lambda self, context: update_message('ex2',"Cancelled"),
            'queue_callback_fatalerror': lambda self, context: update_message('ex2',"Error Occured..."),
        },
        "another_background_tasks" : {
            #define queue tasks
            0: {
                'task_modu_name': "another_test.py",
                'task_pos_args': [0,],
                'task_kw_args': {},
                'task_fn_name': "my_looong_task",
                'task_callback_pre': lambda self, context: update_message('ex22',"StartingLoong2.."),
                'task_callback_post': lambda self, context, result: update_message('ex22',"Was Very Loooong!"),
            },
            1: {
                'task_modu_name': "my_standalone_worker.py",
                'task_pos_args': [2,],
                'task_kw_args': {},
                'task_fn_name': "mytask",
                'task_callback_pre': lambda self, context: update_message('ex22',"StartingRest2.."),
                'task_callback_post': lambda self, context, result: update_message('ex22',"Very Nice2!"),
            },
            2: {
                'task_modu_name': "my_standalone_worker.py",
                'task_pos_args': ['USE_TASK_RESULT|0|0',], #Use result from task 0, result[0]
                'task_kw_args': {"printhis": "Hello There!"},
                'task_fn_name': "mytask",
                'task_callback_pre': lambda self, context: update_message('ex22',"King of2?"),
                'task_callback_post': lambda self, context, result: update_message('ex22',"King of the Castle2!"),
            },
            3: {
                'task_modu_name': "another_test.py",
                'task_pos_args': ['USE_TASK_RESULT|1|0',],  #Use result from task 1, result[0]
                'task_kw_args': {},
                'task_fn_name': "myfoo",
                'task_callback_pre': lambda self, context: update_message('ex22',"Almost there2.."),
                'task_callback_post': lambda self, context, result: update_message('ex22',"Done2!"),
            },
            #define queue callbacks
            'queue_callback_pre': lambda self, context: update_message('ex22',"Start Q2!"),
            'queue_callback_post': lambda self, context, results: update_message('ex22',"All Done2!"),
            'queue_callback_cancel': lambda self, context: update_message('ex22',"Cancelled2"),
            'queue_callback_fatalerror': lambda self, context: update_message('ex22',"Error Occured2..."),
        },
    }

###############################
### Parallel Tasks Example ###

class MULTIPROCESS_OT_myparalleltasks(ParallelQueueProcessingModalMixin, bpy.types.Operator):

    bl_idname = "multiprocess.myparalleltasks"
    bl_label = "Launch Parallel Tasks"
    bl_description = "Launch Parallel Tasks with complex dependency tree"

    queues = {
        "my_complex_parallel_tasks" : {
            # First wave, independent tasks
            100000541: {
                'task_modu_name':  "my_parallel_worker.py",
                'task_pos_args': [1, "DataA"],
                'task_kw_args': {"delay": 2.0},
                'task_fn_name': "process_data",
                'task_callback_pre': lambda self, context: update_parallel_task_status(100000541, "running"),
                'task_callback_post': lambda self, context, result: update_parallel_task_status(100000541, "completed"),
            },
            11111110: {
                'task_modu_name':  "my_parallel_worker.py",
                'task_pos_args': [2, "DataB"],
                'task_kw_args': {"delay": 1.5},
                'task_fn_name': "process_data",
                'task_callback_pre': lambda self, context: update_parallel_task_status(11111110, "running"),
                'task_callback_post': lambda self, context, result: update_parallel_task_status(11111110, "completed"),
            },
            22234: {
                'task_modu_name':  "my_parallel_worker.py",
                'task_pos_args': [3, "DataC"],
                'task_kw_args': {"delay": 2.5},
                'task_fn_name': "process_data",
                'task_callback_pre': lambda self, context: update_parallel_task_status(22234, "running"),
                'task_callback_post': lambda self, context, result: update_parallel_task_status(22234, "completed"),
            },
            3333345: {
                'task_modu_name':  "my_parallel_worker.py",
                'task_pos_args': [4, "DataD"],
                'task_kw_args': {"delay": 1.0},
                'task_fn_name': "process_data",
                'task_callback_pre': lambda self, context: update_parallel_task_status(3333345, "running"),
                'task_callback_post': lambda self, context, result: update_parallel_task_status(3333345, "completed"),
            },
            44445651: {
                'task_modu_name':  "my_parallel_worker.py",
                'task_pos_args': [5, "DataE"],
                'task_kw_args': {"delay": 1.8},
                'task_fn_name': "process_data",
                'task_callback_pre': lambda self, context: update_parallel_task_status(44445651, "running"),
                'task_callback_post': lambda self, context, result: update_parallel_task_status(44445651, "completed"),
            },
            
            # Second wave, depend on independent tasks
            55555551: {
                'task_modu_name':  "my_parallel_worker.py",
                'task_pos_args': ['USE_TASK_RESULT|100000541|0', 'USE_TASK_RESULT|11111110|0'],
                'task_kw_args': {"operation": "combine"},
                'task_fn_name': "combine_results",
                'task_callback_pre': lambda self, context: update_parallel_task_status(55555551, "running"),
                'task_callback_post': lambda self, context, result: update_parallel_task_status(55555551, "completed"),
            },
            66766 : {
                'task_modu_name':  "my_parallel_worker.py",
                'task_pos_args': ['USE_TASK_RESULT|22234|0', 'USE_TASK_RESULT|3333345|0', 'USE_TASK_RESULT|44445651|0'],
                'task_kw_args': {"operation": "merge"},
                'task_fn_name': "combine_results",
                'task_callback_pre': lambda self, context: update_parallel_task_status(66766, "running"),
                'task_callback_post': lambda self, context, result: update_parallel_task_status(66766, "completed"),
            },
            
            # Third wave, depend on second wave
            777895: {
                'task_modu_name':  "my_parallel_worker.py",
                'task_pos_args': ['USE_TASK_RESULT|55555551|0', 'USE_TASK_RESULT|66766|0'],
                'task_kw_args': {},
                'task_fn_name': "analyze_data",
                'task_callback_pre': lambda self, context: update_parallel_task_status(777895, "running"),
                'task_callback_post': lambda self, context, result: update_parallel_task_status(777895, "completed"),
            },

            #define queue callbacks
            'queue_callback_pre': lambda self, context: init_parallel_task_tracking(),
            'queue_callback_post': lambda self, context, results: finalize_parallel_tasks(results),
            'queue_callback_cancel': lambda self, context: finalize_parallel_tasks('Cancelled'),
            'queue_callback_fatalerror': lambda self, context: update_message('ex3', "Error Occurred..."),
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
    'ex22': "Background Queue Infos2..",
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
PARALLEL_TASK_STATUS = {}  # {task_id: "pending"|"running"|"completed"|"error"}

def init_parallel_task_tracking():
    """Initialize tracking for all parallel tasks"""
    global PARALLEL_TASK_STATUS
    PARALLEL_TASK_STATUS = {i: "pending" for i in range(9)}  # Tasks 0-8
    update_message('ex3', "Initializing parallel tasks...")
    tag_redraw_all()
    return None

def update_parallel_task_status(task_id, status):
    """Update status of a specific task"""
    global PARALLEL_TASK_STATUS
    PARALLEL_TASK_STATUS[task_id] = status
    
    # Count completed tasks
    completed = sum(1 for s in PARALLEL_TASK_STATUS.values() if s == "completed")
    total = len(PARALLEL_TASK_STATUS)
    
    if completed == total:
        update_message('ex3', f"All tasks completed! ({completed}/{total})")
    else:
        running = sum(1 for s in PARALLEL_TASK_STATUS.values() if s == "running")
        update_message('ex3', f"Progress: {completed}/{total} completed, {running} running. ({MULTIPROCESSING_ALLOCATED_CORES} cores)")
    
    tag_redraw_all()
    return None

def finalize_parallel_tasks(results):
    """Called when all parallel tasks are finished"""
    if results=='Cancelled':
        update_message('ex3', f"Cancelled..")    
        tag_redraw_all()
        global PARALLEL_TASK_STATUS
        PARALLEL_TASK_STATUS = {}
        return None    
    update_message('ex3', f"All {len(results)} parallel tasks completed successfully!")
    tag_redraw_all()
    return None

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
        
        cls = MULTIPROCESS_OT_myblockingqueue
        identifier = "my_blocking_tasks"
        currently_running = cls.is_running(identifier)

        box = layout.box()
        rwoo = box.row(align=True)
        rwoo.scale_y = 1.3
        butrun = rwoo.row(align=True)
        butrun.enabled = not currently_running
        op = butrun.operator(cls.bl_idname, text="Launch Blocking Queue!", icon='PLAY')
        op.queue_identifier = identifier
        if (currently_running):
            butcanc = rwoo.row(align=True)
            op = butcanc.operator(cls.bl_idname, text="", icon='PANEL_CLOSE')
            op.queue_identifier = identifier ; op.send_cancel_request = True
        #
        box.separator(type='LINE')
        if MYPROGRESS['ex1']>0:
            box.progress(text=MYMESSAGES['ex1'], factor=MYPROGRESS['ex1'], type='BAR')
        else:
            box.label(text=MYMESSAGES['ex1'])
            
        ###########################################
        #Example 2: Non blocking background queue, no access to bpy..
        
        cls = MULTIPROCESS_OT_mybackgroundqueue

        identifier = "my_background_tasks"
        currently_running = cls.is_running(identifier)
        #
        box = layout.box()
        rwoo = box.row(align=True)
        rwoo.scale_y = 1.3
        butrun = rwoo.row(align=True)
        butrun.enabled = not currently_running
        op = butrun.operator(cls.bl_idname, text="Launch Background Queue!", icon='PLAY')
        op.queue_identifier = identifier
        if (currently_running):
            butcanc = rwoo.row(align=True)
            op = butcanc.operator(cls.bl_idname, text="", icon='PANEL_CLOSE')
            op.queue_identifier = identifier ; op.send_cancel_request = True
        #
        box.separator(type='LINE')
        box.label(text=MYMESSAGES['ex2'])

        identifier = "another_background_tasks"
        currently_running = cls.is_running(identifier)
        #
        box = layout.box()
        rwoo = box.row(align=True)
        rwoo.scale_y = 1.3
        butrun = rwoo.row(align=True)
        butrun.enabled = not currently_running
        op = butrun.operator(cls.bl_idname, text="Launch Another Queue!", icon='PLAY')
        op.queue_identifier = identifier
        if (currently_running):
            butcanc = rwoo.row(align=True)
            op = butcanc.operator(cls.bl_idname, text="", icon='PANEL_CLOSE')
            op.queue_identifier = identifier ; op.send_cancel_request = True
        #
        box.separator(type='LINE')
        box.label(text=MYMESSAGES['ex22'])

        ###########################################
        #Example 3: Parallel tasks with wave visualization
        
        cls = MULTIPROCESS_OT_myparalleltasks
        identifier = "my_complex_parallel_tasks"
        currently_running = cls.is_running(identifier)

        box = layout.box()
        rwoo = box.row(align=True)
        rwoo.scale_y = 1.3
        butrun = rwoo.row(align=True)
        butrun.enabled = not currently_running
        op = butrun.operator(cls.bl_idname, text="Launch Parallel Tasks!", icon='PLAY')
        op.queue_identifier = identifier
        if (currently_running):
            butcanc = rwoo.row(align=True)
            op = butcanc.operator(cls.bl_idname, text="", icon='PANEL_CLOSE')
            op.queue_identifier = identifier ; op.send_cancel_request = True

        box.separator(type='LINE')

        # Task wave visualization
        if (PARALLEL_TASK_STATUS):
            wave_box = box.box()
            wave_box.label(text="Tasks Execution Waves:", icon='NETWORK_DRIVE')
            split = wave_box.split(factor=0.33)
            # Wave 0 column
            col0 = split.column()
            for task_id in [100000541, 11111110, 22234, 3333345, 44445651]:
                status = PARALLEL_TASK_STATUS.get(task_id, "pending")
                icon = {'pending': 'PAUSE', 'running': 'PLAY', 'completed': 'CHECKMARK', 'error': 'ERROR'}[status]
                row = col0.row()
                row.label(text=f"{task_id}", icon=icon)
            # Wave 1 column
            col1 = split.column()
            for task_id in [55555551, 66766]:
                status = PARALLEL_TASK_STATUS.get(task_id, "pending")
                icon = {'pending': 'PAUSE', 'running': 'PLAY', 'completed': 'CHECKMARK', 'error': 'ERROR'}[status]
                row = col1.row()
                row.label(text=f"{task_id}", icon=icon)
            # Wave 2 column  
            col2 = split.column()
            for task_id in [777895]:
                status = PARALLEL_TASK_STATUS.get(task_id, "pending")
                icon = {'pending': 'PAUSE', 'running': 'PLAY', 'completed': 'CHECKMARK', 'error': 'ERROR'}[status]
                row = col2.row()
                row.label(text=f"{task_id}", icon=icon)
        
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

    #create a new multiprocessing pool with 90% of the available cores (when blender is done initializing..)
    def wait_restrict_state_timer():
        if (str(bpy.context).startswith("<bpy_restrict_state")): 
            return 0.05
        multiproc_init(process_alloc=90)
        return None
    bpy.app.timers.register(wait_restrict_state_timer)

    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    multiproc_deinit()
