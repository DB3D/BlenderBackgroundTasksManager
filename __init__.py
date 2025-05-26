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


class MULTIPROCESS_PT_panel(bpy.types.Panel):
    bl_label = "Multiprocess"
    bl_idname = "MULTIPROCESS_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Multiprocess"
    def draw(self, context):
        op = self.layout.operator("multiprocess.launch_background_tasks", text="Launch Multiprocess Modal!!!!", icon='PLAY')
        op.queue_identifier = "my_series_of_tasks"


FILENAME = os.path.join(os.path.dirname(__file__), "backgroundtasks", "my_standalone_worker.py")


class MULTIPROCESS_OT_launch_background_tasks(bpy.types.Operator):

    bl_idname = "multiprocess.launch_background_tasks"
    bl_label = "Launch Multiprocess"
    bl_description = "Start parallel processing"

    queue_identifier : bpy.props.StringProperty(
        default="",
        description="Identifier for the process, in order to retrieve queue instruction for this process in cls.queue",
        )

    # NOTE: about the queue parameter:
    #
    # Usage:
    # change MULTIPROCESS_OT_launch_background_tasks.queue dict before calling the operation to add your own tasks!
    # make sure to set self.queue_identifier and that this value is present in the queue dict.
    #
    # Expected format:
    #  <identifier>: {    NOTE: perhaps you wish to run this operator simultaneously with multiple processes? that is why we need to identigy your queue, will equal to the passed self.queue_identifier
    #     <index>: {      NOTE: The task index, int starting at 0.
    #         'script_path': <path to script>,                 NOTE: the script path where your function is located. This module shall be totally indpeendent from blender!
    #         'positional_args': [<args>],                     NOTE: these values must be pickeable (bpy independant)!
    #         'keyword_args': {'<kwarg_name>': <kwarg_value>}, NOTE: same here
    #         'function_name': "<function_name>",              NOTE: the name of the function you wish to execute in background
    #                                                                function must be pickleable and found on module top level!
    #         'function_worker': <function_worker>,            NOTE: we'll import and add the function to this emplacement. set it to None.
    #         'function_result': <function_result>,            NOTE: once the function is finished, we'll catch the result and place it here.
    #         'result_callback': <result_callback>,            NOTE: the function to call when the result is ready. args are: (self, context, result) and the function shall return None. 
    #     },                                                         this callback will NOT execute in the main thread, it will be called in the background thread. 
    #                                                                it will block blender UI and can have access to bpy.
    queue = {
        "my_series_of_tasks" : {
            0: {
                'script_path': FILENAME,
                'positional_args': [1,],
                'keyword_args': {},
                'function_name': "mytask",
                'function_worker': None,
                'function_result': None,
                'result_callback': lambda self, context, result: print(f"INFO: callback! {result} for index {self.qidx}"),
            },
            1: {
                'script_path': FILENAME,
                'positional_args': [2,],
                'keyword_args': {},
                'function_name': "mytask",
                'function_worker': None,
                'function_result': None,
                'result_callback': lambda self, context, result: print(f"INFO: callback! {result} for index {self.qidx}"),
            },
            2: {
                'script_path': FILENAME,
                'positional_args': [3,],
                'keyword_args': {},
                'function_name': "mytask",
                'function_worker': None,
                'function_result': None,
                'result_callback': lambda self, context, result: print(f"INFO: callback! {result} for index {self.qidx}"),
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
        
        self.qactive = False #the queue, a dict of tasks of worker functions to be executed
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

    def execute(self, context):
        print("INFO: launch_background_tasks.execute(): Starting multiprocessing..")
        try:
            #make sure the queue identifier is set..
            if (self.queue_identifier not in self.queue):
                print(f"ERROR: launch_background_tasks.execute(): Queue identifier {self.queue_identifier} not found in queue dict.")
                return {'CANCELLED'}
            self.qactive = self.queue[self.queue_identifier]

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
        
            arg = self.qactive[self.qidx]['positional_args'][0] #TODO support passing args & kwargs in there...
            self._awaiting_result = self._pool.map_async(function_worker, [arg],)
        
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
            async_results = self._awaiting_result.get()
            if (async_results is None):
                print(f"ERROR: launch_background_tasks.store_task_result(): Task{self.qidx} finished with no results! Cancelling...")
                return False

            results = async_results[0] #async is always returning a list of results, even if there is only one result
            self.qactive[self.qidx]['function_result'] = results

            print(f"INFO: launch_background_tasks.store_task_result(): Task{self.qidx} finished! Results: {results}")
            return True
            
        except Exception as e:
            print(f"ERROR: launch_background_tasks.store_task_result(): Error getting multiprocessing results: {e}")
            traceback.print_exc()
            return False

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
            
            # does this task has a result callback? if yes call it..
            callback = self.qactive[self.qidx].get('result_callback', None)
            if (callback is not None):
                print(f"INFO: launch_background_tasks.modal(): Calling Task{self.qidx} result callback...")
                try:
                    callback(self, context, self.qactive[self.qidx]['function_result'])
                except Exception as e:
                    print(f"ERROR: launch_background_tasks.modal(): Error calling Task{self.qidx} result callback: {e}")

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
            self._pool.close()  # No more tasks will be submitted
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
