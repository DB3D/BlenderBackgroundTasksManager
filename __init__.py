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
import sys
import uuid
import time
import traceback
import multiprocessing

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
    #         'task_pos_args': [<args_value>],                 NOTE: Arguments to pass to the function.
    #         'task_kw_args': {'<kwarg_name>': <kwarg_value>},       if you'd like to reuse result from a previous task, use notation 'USE_TASK_RESULT|<taskindex>|<result_index>'
    #         'task_function': <function>,                     NOTE: define the function to execute (the function can access bpy)
    #         'task_result': <tuple>,                          NOTE: Once the function is finished, we'll catch the result and place it here. the result will always be a tuple!
    #         'task_callback_pre':    <function>,              NOTE: The function to call before or after the task. args are: (self, context, result) for post and (self, context) for pre. Shall return None. 
    #         'task_callback_post':   <function>,                    callbacks will never execute in background, it will be called in the main thread. 
    #     },                                                         therefore it will block blender UI, but give access to bpy, letting you bridge your background process with blender (ex updating an interface).
    #      NOTE: More optional callbacks! signature: (self, context) & return None. 'queue_callback_post' get an additional argument: results_dict, a dict of all the results of the tasks. key is the task index
    #     'queue_callback_pre': <function>,         NOTE: This callback could be used to build tasks via self (self.queues[self.queue_identifier][task_idx][..]) if needed.
    #     'queue_callback_post': <function>,        NOTE: This callback is to be used to handle the queue after it has been successfully executed.
    #     'queue_callback_fatal_error': <function>, NOTE: This callback is to be used to handle fatal errors, errors that would cancel out the whole queue. (if this happens, 'queue_callback_post' will not be called)
    #  },                                                     therefore it will block blender UI, but give access to bpy, letting you bridge your background process with blender (ex updating an interface).

    queues = {}
    
    #TODO will need to check if this opperator is in the current windows modal before ruinning modal, only one at the time


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
    #         'task_script_path': <path/to/script.py>,         NOTE: The script path where your function is located. This module shall be totally indpeendent from blender!
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
    #  },                                                     therefore it will block blender UI, but give access to bpy, letting you bridge your background process with blender (ex updating an interface).

    queues = {}

    @classmethod
    def define_background_queue(cls, queue_identifier:str, queue_data:dict):
        """Add a queue to the class. Meant for public use.
        or define class.queues[queue_identifier] - .. yourself"""

        tasks_count = 0
        for k,v in queue_data.items():
            if (type(k) is int):

                #ensure these values exists
                assert 'task_script_path' in v, f"ERROR: define_background_queue(): 'task_script_path' is required in queue_data."
                assert 'task_pos_args' in v, f"ERROR: define_background_queue(): 'task_pos_args' is required in queue_data."
                assert 'task_kw_args' in v, f"ERROR: define_background_queue(): 'task_kw_args' is required in queue_data."
                assert 'task_fn_name' in v, f"ERROR: define_background_queue(): 'task_fn_name' is required in queue_data."

                #ensure these two values are by default always set to None
                v['task_fn_worker'] = None
                v['task_result'] = None

                tasks_count += 1
                continue

        if (tasks_count == 0):
            raise ValueError(f"ERROR: define_background_queue(): No tasks found in queue_data.")

        cls.queues[queue_identifier] = queue_data
        return None

    @classmethod
    def start_background_queue(cls, queue_identifier:str):
        """Start a queue of background tasks. Will run bpy.ops. Meant for public use.
        or run the according bpy.ops with the according queue identifier"""

        if (queue_identifier not in cls.queues):
            raise ValueError(f"ERROR: start_background_queue(): Queue identifier {queue_identifier} not found in queue dict. Make sure to use define_background_queue() classmethod function to define a queue first")

        bpy_operator = getattr(bpy.ops, cls.bl_idname)
        assert bpy_operator, f"ERROR: start_background_queue(): Operator '{cls.bl_idname}' not found in bpy.ops."
        bpy_operator(queue_identifier=queue_identifier)

        return None

    def initialize_variables(self):
        """Initialize the operator state variables"""

        self._debugname = self.__class__.bl_idname
        self._modal_timer = None #the modal timer item, important for tracking the currently running background task.
        self._pool = None #the multiprocessing pool, used to run the tasks in parallel.
        self._pool_result = None #the results currently being awaited for the task being processed. the return value of Pool.map_async()
        self._tmp_sys_paths = [] #a list of module paths that were added to sys.path, nead a cleanup when not needed anymore.
        self._tasks_count = 0 #the number of tasks in the queue, indicated by the number of tasks indexes (starting at 0).
        self._all_successfully_finished = False #flag to check if the queue was successfully finished.
        
        self.qactive = None #the queue of tasks corresponding to the queue identifier, a dict of tasks of worker functions to be executed
        self.qidx = 0 #the current index of the task that is being executed
        
        return None

    def import_worker_fct(self, modulefile, function_name):
        """temporarily add module to sys.path, so it can be found by multiprocessing, 
        clearing our any potential bl_ext dependencies issues"""

        if (not os.path.exists(modulefile)):
            print(f"WARNING: {self._debugname}.import_worker_fct(): Module path does not exist: ", modulefile)
            return None
        
        moduledir = os.path.dirname(modulefile)
        modulename = os.path.basename(modulefile).replace(".py", "")

        # add temp module, so our Pool.map_async() can find it without
        # being fcked by 'bl_ext' module dependencies.
        if (moduledir not in sys.path):
            sys.path.insert(0, moduledir)
            # writing in there is bad practice, but it's ok we gonna clean later..
            self._tmp_sys_paths.append(moduledir)

        # Import the standalone worker module
        try:
            exec(f"import {modulename}", globals())
            module_worker = globals()[modulename]
        except Exception as e:
            print(f"ERROR: {self._debugname}.import_worker_fct(): Something went wrong while importing {modulename}: {e}")
            return None

        # Find our function
        function_worker = getattr(module_worker, function_name, None)
        if (not function_worker):
            print(f"ERROR: {self._debugname}.import_worker_fct(): Function {function_name} does not exist in {modulefile}. make sure it's found in the first level of this module.")
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
                function_worker = self.import_worker_fct(v['task_script_path'], v['task_fn_name'])
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

            # initialize a processing pool
            ctx = multiprocessing.get_context('spawn')
            self._pool = ctx.Pool(2)

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

    def start_task(self, context) -> bool:
        """start a task in the pool.
        return True if the task was started successfully, False otherwise."""

        try:
            function_worker = self.qactive[self.qidx]['task_fn_worker']
            if (function_worker is None):
                print(f"ERROR: {self._debugname}.start_task(): Function worker task{self.qidx} was not found!")
                return False

            # get the arguments we need to pass to the function
            args = self.qactive[self.qidx]['task_pos_args']
            kwargs = self.qactive[self.qidx]['task_kw_args']

            # Resolve any result references in args and kwargs
            resolved_args = self.resolve_params_notation(args) if args else []
            resolved_kwargs = self.resolve_params_notation(kwargs) if kwargs else {}

            # call the task_callback_pre function, if exists
            self.exec_callback(context, 'task_callback_pre')

            # Use apply_async instead of map_async - it handles multiple args and kwargs naturally
            self._pool_result = self._pool.apply_async(function_worker, resolved_args, resolved_kwargs)
        
            debugprint(f"INFO: {self._debugname}.start_task(): Task{self.qidx} started!")
            return True
        
        except Exception as e:
            print(f"ERROR: {self._debugname}.start_task(): Error starting background task{self.qidx}: {e}")
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
            succeeded = self.start_task(context)
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

        #close processing pool
        if (self._pool):
            self._pool.close()
            self._pool.join()
            self._pool = None

        #remove result
        if (self._pool_result):
            self._pool_result = None

        # reset counters & idx's
        self.qidx = 0
        self._tasks_count = 0

        #remove temp module from sys.path
        for module_path in self._tmp_sys_paths:
            if (module_path in sys.path):
                sys.path.remove(module_path)
        self._tmp_sys_paths = []

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

    multithread_allocation : bpy.props.IntProperty(
        description="#TODO the percentage of max tasks (threads???)  to be launched simultaneously (in percentage because it varies from machine)",
        default=70,
        min=10,
        max=100,
        )
    taskpile_identifier : bpy.props.StringProperty(
        default="",
        description="Identifier for the process, in order to retrieve queue instruction for this process in cls.queues",
        )

    # NOTE: about the queues parameter:
    ################### Usage: #############################
    #   change cls.queues dict before calling the operation to add your own tasks!
    #   make sure to set self.taskpile_identifier and that this value is present in the queue dict.
    ################### Expected format: ###################
    #  <taskpile_identifier>: {    NOTE: perhaps you wish to run this operator simultaneously with multiple processes? that is why we need to identigy your queue, will equal to the passed self.taskpile_identifier
    #     <taskindex>: {       NOTE: The task index, int starting at 0.
    #         'task_script_path': <path/to/script.py>,         NOTE: The script path where your function is located. This module shall be totally indpeendent from blender!
    #         'task_pos_args': [<args_value>],                 NOTE: Arguments to pass to the function. These values must be pickeable (bpy independant)!
    #         'task_kw_args': {'<kwarg_name>': <kwarg_value>},       if you'd like to reuse result from a previous task, use notation 'USE_TASK_RESULT|<taskindex>|<result_index>' by doing so, paralellization won't be possible for this task!!!
    #         'task_fn_name': "<task_fn_name>",                NOTE: The name of the function you wish to execute in background
    #                                                                the function must be pickleable and found on module top level!
    #         'task_fn_worker': <function>,                    NOTE: We'll import and add the function to this emplacement. Just set it to None!
    #         'task_result': <tuple>,                          NOTE: Once the function is finished, we'll catch the result and place it here. the result will always be a tuple!
    #         'task_callback_pre':    <function>,              NOTE: The function to call before or after the task. args are: (self, context, result) for post and (self, context) for pre. Shall return None. 
    #         'task_callback_post':   <function>,                    callbacks will never execute in background, it will be called in the main thread. 
    #     },                                                         therefore it will block blender UI, but give access to bpy, letting you bridge your background process with blender (ex updating an interface).
    #      NOTE: More optional callbacks! signature: (self, context) & return None. 'queue_callback_post' get an additional argument: results_dict, a dict of all the results of the tasks. key is the task index
    #     'taskspile_callback_pre': <function>,         NOTE: This callback could be used to build tasks via self (self.queues[self.taskpile_identifier][task_idx][..]) if needed.
    #     'taskspile_callback_post': <function>,        NOTE: This callback is to be used to handle the queue after it has been successfully executed.
    #     'taskspile_callback_fatal_error': <function>, NOTE: This callback is to be used to handle fatal errors, errors that would cancel out the whole queue. (if this happens, 'queue_callback_post' will not be called)
    #  },                                                     therefore it will block blender UI, but give access to bpy, letting you bridge your background process with blender (ex updating an interface).

    taskpiles = {}

    def initialize_variables(self):
        """Initialize the operator state variables"""

        self._debugname = self.__class__.bl_idname
        self._modal_timer = None #the modal timer item, important for tracking the currently running background task.
        self._pool = None #the multiprocessing pool, used to run the tasks in parallel.
        self._pool_result = None #the results currently being awaited for the task being processed. the return value of Pool.map_async()
        self._tmp_sys_paths = [] #a list of module paths that were added to sys.path, nead a cleanup when not needed anymore.
        self._tasks_count = 0 #the number of tasks in the queue, indicated by the number of tasks indexes (starting at 0).
        self._all_successfully_finished = False #flag to check if the queue was successfully finished.

        self.pileactive = None #the queue of tasks corresponding to the taskpile_identifier, a dict of tasks of worker functions to be executed
        self.subqueues = [] #some tasks might be co-dependent if using the 'USE_TASK_RESULT' notation. therefore we may need to manage multiple queue in parallel
        
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
# Implementation Example

def tag_redraw_all():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return None

MYMESSAGE = "Hello There!"

def update_message(message):
    global MYMESSAGE
    MYMESSAGE = message
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
        
        button = layout.column()
        button.scale_y = 1.3
        op = button.operator("multiprocess.mybackgroundqueue", text="Launch Background Queue!", icon='PLAY')
        op.queue_identifier = "my_series_of_tasks"

        layout.separator(type='LINE')
        layout.label(text=MYMESSAGE)

        return None

BACKGROUND_TASKS_DIR = os.path.join(os.path.dirname(__file__), "backgroundtasks")

class MULTIPROCESS_OT_mybackgroundqueue(BackgroundQueueProcessingModalMixin, bpy.types.Operator):
    
    bl_idname = "multiprocess.mybackgroundqueue"
    bl_label = "Launch Background Tasks"
    bl_description = "Launch Background Tasks"

    queues = {
        "my_series_of_tasks" : {
            #define queue tasks
            0: {
                'task_script_path': os.path.join(BACKGROUND_TASKS_DIR, "my_standalone_worker.py"),
                'task_pos_args': [3,],
                'task_kw_args': {},
                'task_fn_name': "mytask",
                'task_fn_worker': None,
                'task_result': None,
                'task_callback_pre': lambda self, context: print("task_callback_pre..."),
                'task_callback_post': lambda self, context, result: update_message("Very Nice!"),
            },
            1: {
                'task_script_path': os.path.join(BACKGROUND_TASKS_DIR, "my_standalone_worker.py"),
                'task_pos_args': ['USE_TASK_RESULT|0|0',], #Use result from task 0, index 0
                'task_kw_args': {"printhis": "Hello There!"},
                'task_fn_name': "mytask",
                'task_fn_worker': None,
                'task_result': None,
                'task_callback_pre': lambda self, context: print("task_callback_pre..."),
                'task_callback_post': lambda self, context, result: update_message("King of the Castle!"),
            },
            2: {
                'task_script_path': os.path.join(BACKGROUND_TASKS_DIR, "another_test.py"),
                'task_pos_args': ['USE_TASK_RESULT|1|0',],  #Use result from task 1, index 0
                'task_kw_args': {},
                'task_fn_name': "myfoo",
                'task_fn_worker': None,
                'task_result': None,
                'task_callback_pre': lambda self, context: print("task_callback_pre..."),
                'task_callback_post': lambda self, context, result: update_message("Done!"),
            },
            #define queue callbacks
            'queue_callback_pre': lambda self, context: print("Callback: Before queue"),
            'queue_callback_post': lambda self, context, results: update_message("All Done!"),
            'queue_callback_fatal_error': lambda self, context: update_message("Error Occured..."),
        }
    }

classes = [
    MULTIPROCESS_OT_mybackgroundqueue,
    MULTIPROCESS_PT_panel,
    ]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
