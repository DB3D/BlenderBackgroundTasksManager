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



MY_MESSAGE = "Hello There!"

def update_message(message):

    global MY_MESSAGE
    MY_MESSAGE = message
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()

class MULTIPROCESS_PT_panel(bpy.types.Panel):

    bl_label = "Multiprocess"
    bl_idname = "MULTIPROCESS_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Multiprocess"

    def draw(self, context):
        layout = self.layout
        op = layout.operator("multiprocess.launch_background_tasks", text="Launch Multiprocess Modal!!!!", icon='PLAY')
        op.queue_identifier = "my_series_of_tasks"
        layout.label(text=MY_MESSAGE)


BACKGROUND_TASKS_DIR = os.path.join(os.path.dirname(__file__), "backgroundtasks")


class MULTIPROCESS_OT_launch_background_tasks(bpy.types.Operator):

    bl_idname = "multiprocess.launch_background_tasks"
    bl_label = "Launch Multiprocess"
    bl_description = "Start parallel processing"

    queue_identifier : bpy.props.StringProperty(
        default="",
        description="Identifier for the process, in order to retrieve queue instruction for this process in cls.queues",
        )

    # NOTE: about the queues parameter:
    #
    # Usage:
    #   change MULTIPROCESS_OT_launch_background_tasks.queues dict before calling the operation to add your own tasks!
    #   make sure to set self.queue_identifier and that this value is present in the queue dict.
    #
    # Expected format:
    #    <queueidentifier>: {   NOTE: perhaps you wish to run this operator simultaneously with multiple processes? that is why we need to identigy your queue, will equal to the passed self.queue_identifier
    #       <taskindex>: {      NOTE: The task index, int starting at 0.
    #           'script_path': <path to script>,                 NOTE: the script path where your function is located. This module shall be totally indpeendent from blender!
    #           'positional_args': [<args>],                     NOTE: arguments to pass to the function. These values must be pickeable (bpy independant)!
    #           'keyword_args': {'<kwarg_name>': <kwarg_value>},       if you'd like to reuse result from a preview task, use notation 'RESULTS|<taskindex>|<result_index>'
    #           'function_name': "<function_name>",              NOTE: the name of the function you wish to execute in background
    #                                                                  function must be pickleable and found on module top level!
    #           'function_worker': <function>,                   NOTE: we'll import and add the function to this emplacement. set it to None.
    #           'function_result': <tuple>,                      NOTE: once the function is finished, we'll catch the result and place it here. the result will always be a tuple!
    #           'callback_pre':    <function>,                   NOTE: the function to call when the result is ready. args are: (self, context, result) and the function shall return None. 
    #           'callback_post':   <function>,                         callbacks will never execute in the main thread, it will be called in the background thread. 
    #       },                                                         it will block blender UI and can have access to bpy.

    queues = {
        "my_series_of_tasks" : {
            0: {
                'script_path': os.path.join(BACKGROUND_TASKS_DIR, "my_standalone_worker.py"),
                'positional_args': [3],  # First positional arg for mytask(v, printhis=None)
                'keyword_args': {},  # Keyword argument
                'function_name': "mytask",
                'function_worker': None,
                'function_result': None,
                'callback_pre': lambda self, context: print("callback_pre..."),
                'callback_post': lambda self, context, result: update_message("Very Nice!"),
            },
            1: {
                'script_path': os.path.join(BACKGROUND_TASKS_DIR, "my_standalone_worker.py"),
                'positional_args': ['RESULTS|0|0',], #SpecialNotation: Use result from task 0, index 0
                'keyword_args': {"printhis": "Hello There!"},
                'function_name': "mytask",
                'function_worker': None,
                'function_result': None,
                'callback_pre': lambda self, context: print("callback_pre..."),
                'callback_post': lambda self, context, result: update_message("King of the Castle!"),
            },
            2: {
                'script_path': os.path.join(BACKGROUND_TASKS_DIR, "another_test.py"),
                'positional_args': ['RESULTS|1|0'],  #SpecialNotation: Use result from task 1, index 0
                'keyword_args': {},
                'function_name': "myfoo",
                'function_worker': None,
                'function_result': None,
                'callback_pre': lambda self, context: print("callback_pre..."),
                'callback_post': lambda self, context, result: update_message("Done!"),
            }
        }
    }

    def __init__(self, *args, **kwargs):        
        print("INFO: MULTIPROCESS_OT_launch_background_tasks.__init__()")
        super().__init__(*args, **kwargs)

        self._pool = None #the multiprocessing pool, used to run the tasks in parallel.
        self._modal_timer = None #the modal timer item, important for tracking the currently running background task.
        self._awaiting_result = None #the results currently being awaited for the task being processed. the return value of Pool.map_async()
        self._tmp_sys_paths = [] #a list of module paths that were added to sys.path, nead a cleanup when not needed anymore.
        
        self.qactive = False #the queue of tasks corresponding to the queue identifier, a dict of tasks of worker functions to be executed
        self.qidx = 0 #the current index of the task that is being executed

    def import_worker_fct(self, modulefile, function_name):
        """temporarily add module to sys.path, so it can be found by multiprocessing, 
        clearing our any potential bl_ext dependencies issues"""

        if (not os.path.exists(modulefile)):
            print("WARNING: Module path does not exist: ", modulefile)
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
            print(f"ERROR: Something went wrong while importing {modulename}: {e}")
            return None

        # Find our function
        function_worker = getattr(module_worker, function_name, None)
        if (not function_worker):
            print(f"ERROR: Function {function_name} does not exist in {modulefile}. make sure it's found in the first level of this module.")
            return None

        return function_worker

    def collect_worker_fcts(self, context) -> int:
        """create a queue of functions to be executed. 
        return the number of valid worker functions found. Should always be equal to the number of tasks in the queue."""

        valid_worker_found = 0
        for k,v in self.qactive.items():
            function_worker = self.import_worker_fct(v['script_path'], v['function_name'])
            if (function_worker is not None):
                self.qactive[k]['function_worker'] = function_worker
                valid_worker_found += 1

        return valid_worker_found

    def resolve_params_notation(self, paramargs):
        """Resolve result references in args/kwargs, when using the 'RESULTS|<taskindex>|<result_index>' notation for a value."""
        
        def resolve_notation(notation):
            """Resolve a single result reference."""
            
            parts = notation.split('|')
            if (len(parts) != 3):
                raise ValueError(f"ERROR: resolve_notation(): Invalid reference notation: {notation}")
            
            task_idx = int(parts[1])
            result_idx = int(parts[2])
            if (task_idx not in self.qactive):
                raise ValueError(f"ERROR: resolve_notation(): Task index {task_idx} not found in queue: {self.qactive}")
            result = self.qactive[task_idx]['function_result']
            if (result is None):
                raise ValueError(f"ERROR: resolve_notation(): Task{task_idx} results are None! Perhaps it's not ready yet, or perhaps this task return None.")
            try:
                value = self.qactive[task_idx]['function_result'][result_idx]
            except Exception as e:
                raise ValueError(f"ERROR: resolve_notation(): Invalid result index: {result_idx} for task {task_idx}: {e}")
            return value
        
        match paramargs:
            case list():
                resolved = []
                for value in paramargs:
                    if (isinstance(value, str) and value.startswith('RESULTS|')):
                            resolved.append(resolve_notation(value))
                    else: resolved.append(value)
                return resolved
            
            case dict():
                resolved = {}
                for key, value in paramargs.items():
                    if (isinstance(value, str) and value.startswith('RESULTS|')):
                            resolved[key] = resolve_notation(value)
                    else: resolved[key] = value
                return resolved
            
            case _:
                raise ValueError(f"ERROR: resolve_params_notation(): Invalid argument type: {type(paramargs)} for task {self.qidx}")

    def execute(self, context):
        print("INFO: launch_background_tasks.execute(): Starting multiprocessing..")
        try:
            #make sure the queue identifier is set..
            if (self.queue_identifier not in self.queues):
                print(f"ERROR: launch_background_tasks.execute(): Queue identifier {self.queue_identifier} not found in queue dict.")
                return {'CANCELLED'}
            self.qactive = self.queues[self.queue_identifier]

            # create the function queue
            valid_worker_found = self.collect_worker_fcts(context)
            if (len(self.qactive) != valid_worker_found):
                print("ERROR: launch_background_tasks.execute(): We couldn't find all the worker functions for your queue.")
                return {'CANCELLED'}

            # initialize a processing pool
            ctx = multiprocessing.get_context('spawn')
            self._pool = ctx.Pool(2)

            # Start modal operation
            self._modal_timer = context.window_manager.event_timer_add(0.15, window=context.window)
            context.window_manager.modal_handler_add(self)
            print("INFO: launch_background_tasks.execute(): Running modal..")
            return {'RUNNING_MODAL'}

        except Exception as e:
            print(f"ERROR: launch_background_tasks.execute(): Error starting multiprocessing: {e}")
            traceback.print_exc()
            return {'CANCELLED'}

    def start_task(self, context) -> bool:
        """start a task in the pool.
        return True if the task was started successfully, False otherwise."""

        try:
            function_worker = self.qactive[self.qidx]['function_worker']
            if (function_worker is None):
                print(f"ERROR: launch_background_tasks.start_task(): Function worker task{self.qidx} was not found!")
                return False

            # get the arguments we need to pass to the function
            args = self.qactive[self.qidx]['positional_args']
            kwargs = self.qactive[self.qidx]['keyword_args']

            # Resolve any result references in args and kwargs
            resolved_args = self.resolve_params_notation(args) if args else []
            resolved_kwargs = self.resolve_params_notation(kwargs) if kwargs else {}

            # call the callback_pre function, if exists
            self.call_callback(context, 'callback_pre')

            # Use apply_async instead of map_async - it handles multiple args and kwargs naturally
            self._awaiting_result = self._pool.apply_async(function_worker, resolved_args, resolved_kwargs)
        
            print(f"INFO: launch_background_tasks.start_task(): Task{self.qidx} started!")
            return True
        
        except Exception as e:
            print(f"ERROR: launch_background_tasks.start_task(): Error starting background task{self.qidx}: {e}")
            traceback.print_exc()
            return False

    def store_task_result(self, context) -> bool:
        """store the result of the task in the queue.
        return True if the result was stored successfully, False otherwise."""

        try:
            result = self._awaiting_result.get()

            # Ensure result is always stored as a tuple for consistent indexing
            if (not isinstance(result, tuple)):
                result = (result,)
            
            self.qactive[self.qidx]['function_result'] = result

            print(f"INFO: launch_background_tasks.store_task_result(): Task{self.qidx} finished! Results: {result}")
            return True
            
        except Exception as e:
            print(f"ERROR: launch_background_tasks.store_task_result(): Error getting multiprocessing results: {e}")
            traceback.print_exc()
            return False

    def call_callback(self, context, callback_identifier=None,):
        """call the callback function for the current task."""
        
        match callback_identifier:

            case 'callback_post':
                callback = self.qactive[self.qidx].get('callback_post', None)
                if (callback is not None):
                    print(f"INFO: launch_background_tasks.modal(): Calling Task{self.qidx} result callback...")
                    try:
                        callback(self, context, self.qactive[self.qidx]['function_result'])
                    except Exception as e:
                        print(f"ERROR: launch_background_tasks.modal(): Error calling Task{self.qidx} result callback: {e}")

            case 'callback_pre':
                callback = self.qactive[self.qidx].get('callback_pre', None)
                if (callback is not None):
                    print(f"INFO: launch_background_tasks.modal(): Calling Task{self.qidx} pre callback...")
                    try:
                        callback(self, context)
                    except Exception as e:
                        print(f"ERROR: launch_background_tasks.modal(): Error calling Task{self.qidx} pre callback: {e}")
        return None

    def modal(self, context, event):

        # Check if processing is complete
        if (event.type!='TIMER'):
            return {'PASS_THROUGH'}

        # if a queue is empty, it means a task is waiting to be done!
        if (self._awaiting_result is None):

            # if we are at the end of the queue, we can finish the modal
            if (self.qidx >= len(self.qactive)):
                return self.finish(context)

            # if not, we start a new task
            succeeeded = self.start_task(context)
            if (not succeeeded):
                return {'CANCELLED'}

            return {'PASS_THROUGH'}

        # do we have a task finished? get the results
        if (self._awaiting_result.ready()):

            succeeeded = self.store_task_result(context)
            if (not succeeeded):
                return {'CANCELLED'}

            # handle callback functions if exists..
            self.call_callback(context, 'callback_post')

            # set up environement for the next task
            self.qidx += 1
            self._awaiting_result = None

            return {'PASS_THROUGH'}

        return {'PASS_THROUGH'}

    def finish(self, context):

        print("INFO: launch_background_tasks.finish(): All tasks finished! Results:")
        for k,v in self.qactive.items():
            print(f"     Task{k}: {v['function_result']}")

        return {'FINISHED'}                    
        
    def cleanup(self, context):
        
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
        if (self._awaiting_result):
            self._awaiting_result = None

        # reset queue idx
        self.qidx = 0

        #remove temp module from sys.path
        for module_path in self._tmp_sys_paths:
            if (module_path in sys.path):
                sys.path.remove(module_path)
        self._tmp_sys_paths = []

        print("INFO: launch_background_tasks.cleanup(): clean up done")
        return None

    def __del__(self):
        print("INFO: launch_background_tasks.__del__()")
        self.cleanup(bpy.context)
        


classes = [
    MULTIPROCESS_OT_launch_background_tasks,
    MULTIPROCESS_PT_panel,
    ]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
