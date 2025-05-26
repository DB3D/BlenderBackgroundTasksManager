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
FUNCNAME = "mytask"


class MULTIPROCESS_OT_launch_background_tasks(bpy.types.Operator):
    bl_idname = "multiprocess.launch_background_tasks"
    bl_label = "Launch Multiprocess"
    bl_description = "Start parallel processing"

    TASKS = {
        'one': {
            'script_path': FILENAME,
            'function_name': "mytask",
        },
        'two': {
            'script_path': FILENAME,
            'function_name': "mytask",
        }
    }

    def __init__(self, *args, **kwargs):        
        print("init")
        super().__init__(*args, **kwargs)

        self.pool = None
        self.modal_timer = None
        self.async_result = None
        self.tmp_sys_paths = []
        self.queue = []

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

        for k,v in self.TASKS.items():
            function_worker = self.import_task_fct(v['script_path'], v['function_name'])
            if (function_worker is None):
                self.queue.append(function_worker)

        return None

    def execute(self, context):
        print("=== Starting Multiprocessing ===")
        try:

            # create the function queue
            #self.create_task_queue(context)
            
            function_worker = self.import_task_fct(FILENAME, FUNCNAME)
            if (function_worker is None):
                return {'CANCELLED'}
            
            # Use spawn method for safety in GUI applications like Blender
            ctx = multiprocessing.get_context('spawn')
            self.pool = ctx.Pool(2)


            self.async_result = self.pool.map_async(function_worker, [1],)

            # Start modal operation
            self.modal_timer = context.window_manager.event_timer_add(1.0, window=context.window)
            context.window_manager.modal_handler_add(self)

            print("=== Task Runnign In Background ===")
            return {'RUNNING_MODAL'}

        except Exception as e:
            print(f"ERROR: Couldn't launch multiprocessing: {e}")
            import tracebackbackgroundtasks
            traceback.print_exc()
            return {'CANCELLED'}

    def modal(self, context, event):

        # Check if processing is complete
        if (event.type!='TIMER'):
            return {'PASS_THROUGH'}

        if (self.async_result.ready()):
            print("=== Task Finished ===")
            try:
                results = self.async_result.get()
                print("timer catch multiprocess end")
                print(f"Results: {results}")
                self.report({'INFO'}, f"Multiprocessing completed! Results: {results}")

            except Exception as e:
                print(f"Error getting multiprocessing results: {e}")
                self.report({'ERROR'}, f"Multiprocessing failed: {str(e)}")

            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def cleanup(self, context):

        print("INFO: launch_background_tasks.cleanup() -start")
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
        if (self.async_result):
            self.async_result = None
        #remove temp module from sys.path
        for module_path in self.tmp_sys_paths:
            if (module_path in sys.path):
                sys.path.remove(module_path)
        self.tmp_sys_paths = []

        print("INFO: launch_background_tasks.cleanup() -end")
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
