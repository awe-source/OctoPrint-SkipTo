# coding=utf-8
from __future__ import absolute_import

### (Don't forget to remove me)
# This is a basic skeleton for your plugin's __init__.py. You probably want to adjust the class name of your plugin
# as well as the plugin mixins it's subclassing from. This is really just a basic skeleton to get you started,
# defining your plugin as a template plugin, settings and asset plugin. Feel free to add or remove mixins
# as necessary.
#
# Take a look at the documentation on what other plugin mixins are available.


import octoprint.plugin
import flask
import json
import re
import os
from flask_babel import gettext as _


class SkipToPlugin(octoprint.plugin.StartupPlugin, 
                   octoprint.plugin.SettingsPlugin,
                   octoprint.plugin.AssetPlugin,
                   octoprint.plugin.TemplatePlugin,
                   ##    octoprint.plugin.ProgressPlugin,
                   octoprint.plugin.BlueprintPlugin, ##this is required otherwise all the routes get 404s...
                   octoprint.plugin.EventHandlerPlugin
                   ):

        
   ##~~ StartupPlugin mixin
    def on_startup(self, host, port):
        self._logger.debug("skipToPlugin has started on %s:%s", host, port)
    
        self.zValue =None
        self.layerCount =None

    
    
    ##~~ SettingsPlugin mixin
    def get_settings_defaults(self):
        return dict(
            use_tempfile=False,
            temp_filename="skipTo_temp.gcode",
            appending_string="_skipTo_{mode}_{value}.gcode"
        )

    
    #~~ TemplatePlugin mixin
    def get_template_configs(self):
        return [
              dict(type="generic", template="skipTo_generic.jinja2", custom_bindings=True),
              dict(type="settings", template="skipTo_settings.jinja2", custom_bindings=False)
        ]
     
 
    ##~~ AssetPlugin mixin

    def get_assets(self):
        # Define your plugin's asset files to automatically include in the
        # core UI here.
        self._logger.debug("Loading assets for skipTo Plugin")
        return {
            "js": ["js/skipTo.js"],
            "css": ["css/skipTo.css"],
            "less": ["less/skipTo.less"]
        }

    ##~~ Softwareupdate hook

    def get_update_information(self):
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://docs.octoprint.org/en/master/bundledplugins/softwareupdate.html
        # for details.
        return {
            "skipTo": {
                "displayName": "SkipTo",
                "displayVersion": self._plugin_version,

                # version check: github repository
                "type": "github_release",
                "user": "awe-source",
                "repo": "OctoPrint-SkipTo",
                "current": self._plugin_version,

                # update method: pip
                "pip": "https://github.com/awe-source/OctoPrint-skipTo/archive/{target_version}.zip",
            }
        }

    def on_event(self, event, payload):
        self._logger.debug(f"got event {event} with payload {json.dumps(payload)}")
        
        if event == "PrintStarted":
            self.layerCount = None
            self.zValue = None
        
        elif event == "Home":
            self.zValue = None
            self.layerCount = None
        
        elif event == "ZChange":
            self.on_z_change(payload)


    def on_z_change(self, payload):

        self.zValue = payload.get('new')
                    
        if payload.get('old') is None:
            # Assume this is layer #0: post home, pre base layer move
            self.layerCount = 0
            self._logger.info("Post home, pre-base layer move detected. Setting layer count to 0.")
        elif self.zValue < payload.get('old', 0):
            # Assume this is layer 1
            self.layerCount = 1
            self._logger.info("Base layer move detected. Setting layer count to 1.")
        else:
            # Increment layer count for subsequent layers
            self.layerCount += 1
            self._logger.info(f"Layer change detected. Incrementing layer count to {self.layerCount}.")
        
        # Send updated values to the frontend
        self._plugin_manager.send_plugin_message(
            self._identifier, 
            {
                "status": {
                    "layerCount": self.layerCount,
                    "zValue": self.zValue
                }
            }
        )

    ##############################################################################
    ## API methods        
        
    def is_blueprint_csrf_protected(self):
        return True
            
    # external api methods
    @octoprint.plugin.BlueprintPlugin.route("/skip_to", methods=["POST"])
    def skip_to(self):
        filepath = flask.request.form.get("filepath", None)
        layer = flask.request.form.get("layer", None)
        z = flask.request.form.get("z", None)

        # Check if filepath is provided
        if not filepath:
            return flask.jsonify(success=False, error="File path is required"), 400

        # Extract origin and path from the provided filepath
        try:
            origin, relative_path = filepath.strip('/').split('/', 1)

            # Map origin to OctoPrint's FileDestinations
            if origin == "local":
                destination = octoprint.filemanager.FileDestinations.LOCAL
            elif origin == "sdcard":
                destination = octoprint.filemanager.FileDestinations.SDCARD
            else:
                self._logger.error(f"Unknown file origin: {origin}")
                return flask.jsonify(success=False, error=f"Unknown file origin: {origin}"), 400

            file_path = self._file_manager.path_on_disk(destination, relative_path)
            self._logger.info(f"Retrieved file path: {file_path}")

        except Exception as e:
            self._logger.error(f"Error retrieving file: {str(e)}")
            return flask.jsonify(success=False, error=f"Could not retrieve file: {str(e)}"), 500

        
        # Validate and process the input
        try:
            if layer is not None:
                layer = int(layer)
                self._logger.info(f"Processing skip to layer: {layer}")
                self._process_skipTo_gcode("layers", layer, file_path)
            elif z is not None:
                z = float(z)
                self._logger.info(f"Processing skip to Z height: {z}")
                self._process_skipTo_gcode("z-height", z, file_path)
            else:
                return flask.jsonify(success=False, error="Either layer or z value must be provided"), 400
        except ValueError as ve:
            self._logger.error(f"Invalid layer or z value: {str(ve)}")
            return flask.jsonify(success=False, error=f"Invalid layer or z value: {str(ve)}"), 400
        except Exception as e:
            self._logger.error(f"Error processing skip to gcode: {str(e)}")
            return flask.jsonify(success=False, error=f"Error processing request: {str(e)}"), 500

        return flask.jsonify(success=True)


    ##############################################################################

    def _process_skipTo_gcode(self, skip_mode, target, src_file_path):
        # Read and modify GCODE to skip layers/zheight
        new_lines = []
        current_layer = 0
        current_z = 0
        skip_reference_point  = 0
        comment = "no comment"
        
        self._logger.info(f"this is the file {src_file_path}")

        with open(src_file_path, "r") as file:
            lines = file.readlines()


            for line in lines:
                # Detect Z-height changes in G-code commands
                if line.startswith("G") and "Z" in line:
                    match = re.search(r"\sZ(\d+\.?\d+)", line)
                    if match:
                        current_z = float(match.group(1))
                # Check for layer markers
                elif ";LAYER" in line and not re.search(r";\s*(layer[\s_-](height|count))", line, re.IGNORECASE):
                    current_layer += 1

                # Only add the line if it is BEFORE layer#1/z0+ 
                # OR greater than or equal to the desired layer/zheight

                #TODO: If this is the "post home/pre layer1" z-move then 
                # we PROBABLY need to move teh Z to be (a little? 20mm?) 
                # above the FIRST Zheight we're going to approach 
                # otehrwise the first move to print position could
                # knock shit over... on tall/complex/broad base models...               

                comparison_value = current_layer if skip_mode == "layers" else current_z
           
                if current_layer<1  or comparison_value >= target:
                    new_lines.append(line)
                    if current_layer > 0:
                        if skip_reference_point == 0:
                            if (skip_mode == "layers"):
                                skip_reference_point = current_z
                                comment = f"REF Z-height {skip_reference_point}"
                            else:
                                skip_reference_point = current_layer
                                comment = f"REF Layer {skip_reference_point}"
                else:
                    # Filter out movement GCODE lines 
                    if not re.match(r"^G\d+", line):
                        new_lines.append(line)

        new_file_path = self._output_lines_to_new_file(src_file_path, new_lines, skip_mode, target, comment)
        
        # Queue the file for printing and start the print
        self._printer.select_file(new_file_path, self._isSdCardFile(new_file_path), True)

        # Optionally send a plugin message about printing state
        self._plugin_manager.send_plugin_message(self._identifier, dict(message= f"{new_file_path} sent to printer..."))
       

    def _isSdCardFile(self, file_path):
        """
        Check if the given file path is on the SD card.
        
        Returns:
            bool: True if the file path contains '/sdcard/', False otherwise.
        """
        return "/sdcard/" in file_path


    def _output_lines_to_new_file(self, src_file_path, lines, mode_description, target_value, comment):
        """
        Writes modified GCODE lines to a new or temporary file and places that file in the queue.
        """
        # Retrieve settings values with proper keys
        use_tempfile = self._settings.get(["use_tempfile"])
        temp_filename = self._settings.get(["temp_filename"])
        appending_string = self._settings.get(["appending_string"])

        if use_tempfile:
            # Ensure the temp file is always placed in the "local/root"
            new_file_path = self._file_manager.path_on_disk(octoprint.filemanager.FileDestinations.LOCAL, temp_filename)
        else:
            suffix = appending_string
            # Remove trailing .gcode (case-insensitive)
            src_file_base, _ = os.path.splitext(src_file_path)
            
            # Replace placeholders in the suffix
            suffix = re.sub(r"{mode}", str(mode_description), suffix)  # Replace {mode} if it exists
            suffix = re.sub(r"{value}", str(target_value), suffix)  # Replace {value} if it exists
            new_file_path = src_file_base + suffix

        # Write the modified GCODE to a new or temporary file
        try:
            with open(new_file_path, "w") as file:
                file.writelines(lines)

            self._logger.info(f"Skip {mode_description} to {target_value} complete. Modified GCODE saved to {new_file_path}. [{comment}]")
            return new_file_path
        except Exception as e:
            self._logger.error(f"Error writing GCODE to file: {str(e)}")
            raise
        
        

# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
__plugin_name__ = "SkipTo"


# Set the Python version your plugin is compatible with below. Recommended is Python 3 only for all new plugins.
# OctoPrint 1.4.0 - 1.7.x run under both Python 3 and the end-of-life Python 2.
# OctoPrint 1.8.0 onwards only supports Python 3.
__plugin_pythoncompat__ = ">=3,<4"  # Only Python 3


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = SkipToPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
