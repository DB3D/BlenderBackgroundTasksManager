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
        self.layout.operator("multiprocess.launch_background_tasks", text="Launch Multiprocess Modal", icon='PLAY')


FILENAME = os.path.join(os.path.dirname(__file__), "backgroundtasks", "my_standalone_worker.py")


class MULTIPROCESS_OT_launch_background_tasks(bpy.types.Operator):
    bl_idname = "multiprocess.launch_background_tasks"
    bl_label = "Launch Multiprocess"
    bl_description = "Start parallel processing"

    # WARNING:
    # pass script paths totally indpeendent from bpy!
    # function and args passed must be pickleable! function must be found on module top level!
    queue = {
        0: {
            'script_path': FILENAME,
            'function_name': "mytask",
            'positional_args': [1,],
            'keyword_args': {},
        },
        1: {
            'script_path': FILENAME,
            'function_name': "mytask",
            'positional_args': [2,],
            'keyword_args': {},
        },
        2: {
            'script_path': FILENAME,
            'function_name': "mytask",
            'positional_args': [3,],
            'keyword_args': {},
        }
    }

    def __init__(self, *args, **kwargs):        
        print("init")
        super().__init__(*args, **kwargs)

        self.pool = None
        self.modal_timer = None
        self.result_waiting = None
        self.tmp_sys_paths = []
        self.queue_idx = 0

    def import_task_fct(self, modulefile, function_name):
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
            self.tmp_sys_paths.append(moduledir)

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

    def create_task_queue(self, context):
        """create a queue of functions to be executed"""

        for k,v in self.queue.items():
            function_worker = self.import_task_fct(v['script_path'], v['function_name'])
            if (function_worker is not None):
                self.queue[k]['function'] = function_worker

        return None

    def execute(self, context):
        print("INFO: launch_background_tasks.execute(): Starting multiprocessing..")
        try:

            # create the function queue
            self.create_task_queue(context)
            if len(self.queue) == 0:
                print("ERROR: launch_background_tasks.execute(): No tasks to execute")
                return {'CANCELLED'}

            # start a processing pool
            ctx = multiprocessing.get_context('spawn')
            self.pool = ctx.Pool(2)

            # Start modal operation
            self.modal_timer = context.window_manager.event_timer_add(0.15, window=context.window)
            context.window_manager.modal_handler_add(self)

            print("INFO: launch_background_tasks.execute(): Running modal..")
            return {'RUNNING_MODAL'}

        except Exception as e:
            print(f"ERROR: launch_background_tasks.execute(): Error starting multiprocessing: {e}")
            traceback.print_exc()
            return {'CANCELLED'}

    def modal(self, context, event):

        # Check if processing is complete
        if (event.type!='TIMER'):
            return {'PASS_THROUGH'}

        # if a queue is empty, it means a task is waiting to be done!
        if (self.result_waiting is None):

            # if we are at the end of the queue, we can finish the modal
            if (self.queue_idx >= len(self.queue)):
                print("INFO: launch_background_tasks.modal(): All tasks finished!")
                return {'FINISHED'}

            # if not, we start a new task
            try:
                function_worker = self.queue[self.queue_idx]['function']
                arg = self.queue[self.queue_idx]['positional_args'][0] #TODO support passing args & kwargs in there...
                self.result_waiting = self.pool.map_async(function_worker, [arg],)
                print(f"INFO: launch_background_tasks.modal(): Task{self.queue_idx} started!")
            except Exception as e:
                print(f"ERROR: launch_background_tasks.modal(): Error starting background task{self.queue_idx}: {e}")

                traceback.print_exc()
                return {'CANCELLED'}

            return {'PASS_THROUGH'}

        # do we have a task finished?
        if (self.result_waiting.ready()):
            try:
                results = self.result_waiting.get()
                print(f"INFO: launch_background_tasks.modal(): Task{self.queue_idx} finished! Results: {results}")
            except Exception as e:
                print(f"ERROR: launch_background_tasks.modal(): Error getting multiprocessing results: {e}")
                return {'CANCELLED'}

            self.queue_idx += 1
            self.result_waiting = None
            return {'PASS_THROUGH'}

        return {'PASS_THROUGH'}

    def cleanup(self, context):
        #remove timer
        if (self.modal_timer):
            context.window_manager.event_timer_remove(self.modal_timer)
            self.modal_timer = None

        #close pool
        if (self.pool):
            self.pool.close()  # No more tasks will be submitted
            self.pool.join()
            self.pool = None

        #remove result
        if (self.result_waiting):
            self.result_waiting = None

        # reset queue
        self.queue = []
        self.queue_idx = 0

        #remove temp module from sys.path
        for module_path in self.tmp_sys_paths:
            if (module_path in sys.path):
                sys.path.remove(module_path)
        self.tmp_sys_paths = []

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
