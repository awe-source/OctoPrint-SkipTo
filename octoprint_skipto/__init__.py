# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import flask
import json
import re
import os
from flask_babel import gettext as _
import urllib.parse


class SkipToPlugin(
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.BlueprintPlugin,
    octoprint.plugin.EventHandlerPlugin,
):
    ##~~ StartupPlugin mixin
    def on_startup(self, host, port):
        self._logger.debug("SkipTo Plugin has started on %s:%s", host, port)
        self.z_value = None
        self.layer_count = None

    ##~~ SettingsPlugin mixin
    def get_settings_defaults(self):
        return {
            "use_tempfile": False,
            "temp_filename": "skipTo_temp.gcode",
            "appending_string": "_skipTo_{mode}{value}.gcode",
            "z_offset": 5.0,
            "ignore_init_gcodes": r"""G0|G1
T\d+
M84
P0
G29""",
        }

    ##~~ TemplatePlugin mixin
    def get_template_configs(self):
        return [
            {"type": "generic", "template": "skipTo_generic.jinja2", "custom_bindings": True},
            {"type": "settings", "template": "skipTo_settings.jinja2", "custom_bindings": False},
        ]

    ##~~ AssetPlugin mixin
    def get_assets(self):
        self._logger.debug("Loading assets for SkipTo Plugin")
        return {
            "js": ["js/skipTo.js"],
            "css": ["css/skipTo.css"],
            "less": ["less/skipTo.less"],
        }


    ##~~ Softwareupdate hook
    def get_update_information(self):
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://docs.octoprint.org/en/master/bundledplugins/softwareupdate.html
        # for details.
        return {
            "SkipTo": {
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

    ##~~ EventHandlerPlugin mixin
    def on_event(self, event, payload):
        self._logger.debug(f"Received event {event} with payload {json.dumps(payload)}")
        if event == "PrintStarted" or event == "Home":
            self.reset_tracking()
        elif event == "ZChange":
            self.on_z_change(payload)

    def reset_tracking(self):
        self.z_value = None
        self.layer_count = None

    def on_z_change(self, payload):
        # Define a minimum layer height to filter out irrelevant changes
        MIN_LAYER_HEIGHT = 0.1  # Adjust based on your printer/slicer settings

        try:
            self.z_value = payload.get("new")
            old_z_value = payload.get("old", None)  # Default to None for clarity

            if old_z_value is None or self.z_value is None:  # Initial layer detection
                self.layer_count = 0
                self._logger.info("Initial Z detected, setting layer count to 0.")
            elif self.z_value < old_z_value:  # Z dropped - potential probing or cleaning activity
                self._logger.warning(
                    f"Unexpected Z drop detected: old_z={old_z_value}, new_z={self.z_value}. Ignoring for layer counting."
                )
            elif abs(self.z_value - old_z_value) < MIN_LAYER_HEIGHT:  # Small Z changes
                self._logger.debug(
                    f"Z change below threshold ({MIN_LAYER_HEIGHT}mm): old_z={old_z_value}, new_z={self.z_value}. Ignoring."
                )
            else:  # Valid layer change
                self.layer_count += 1
                self._logger.info(f"Layer changed, incrementing to {self.layer_count}.")

            # Send plugin message with updated layer and Z info
            self._plugin_manager.send_plugin_message(
                self._identifier,
                {"status": {"layerCount": self.layer_count, "zValue": self.z_value}},
            )
        except Exception as e:
            self._logger.error(f"Error handling Z change: {str(e)}")


    ##############################################################################
    ##~~ API methods
    ##############################################################################
   
       
    def is_blueprint_csrf_protected(self):
        return True
            
    # external api methods
    @octoprint.plugin.BlueprintPlugin.route("/skip_to", methods=["POST"])
    def skip_to(self):
        try:
            filepath = self._get_valid_filepath(flask.request.form.get("filepath"))
            layer = flask.request.form.get("layer")
            z = flask.request.form.get("z")
            start_print = flask.request.form.get("start_print", "false").lower() == "true"
            disable_z_homing = flask.request.form.get("disable_z_homing", "false").lower() == "true"

            layer_value = int(layer) if layer and layer.isdigit() else 0
            z_value = float(z) if z and self._is_float(z) else 0.0

            if layer_value > 0:
                self._process_skip_to_gcode("L", layer_value, filepath, start_print, disable_z_homing)
            elif z_value > 0.0:
                self._process_skip_to_gcode("Z", z_value, filepath, start_print, disable_z_homing)
            else:
                return flask.jsonify(success=False, error="Invalid layer or Z value"), 400

            return flask.jsonify(success=True)
        except ValueError as ve:
            self._logger.error(f"Value error: {str(ve)}")
            return flask.jsonify(success=False, error=str(ve)), 400
        except Exception as e:
            self._logger.error(f"Unexpected error: {str(e)}")
            return flask.jsonify(success=False, error=str(e)), 500
    
    
    def _get_valid_filepath(self, filepath):
        if not filepath:
            raise ValueError("File path is required")
        try:
            filepath = urllib.parse.unquote(filepath)
            origin, relative_path = filepath.strip("/").split("/", 1)
            destination = {"local": octoprint.filemanager.FileDestinations.LOCAL,
                           "sdcard": octoprint.filemanager.FileDestinations.SDCARD}.get(origin)
            if not destination:
                raise ValueError(f"Unknown file origin: {origin}")
            file_path = self._file_manager.path_on_disk(destination, relative_path)
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File does not exist: {file_path}")
            return file_path
        except Exception as e:
            raise ValueError(f"Invalid file path: {str(e)}")


    def _is_float(self, value):
        """Helper function to check if a value can be converted to float."""
        try:
            float(value)
            return True
        except ValueError:
            return False
    ##############################################################################

    def _skip_mode_description(self, skip_mode):
        if skip_mode == "L":
            return "layers"
        elif skip_mode == "Z":
            return "z-height"
        else:
            return "Unknown"

    def _process_skip_to_gcode(self, skip_mode, target, src_file_path, start_print, disable_z_homing):
        # Read and modify GCODE to skip layers/zheight
        output_lines = []
        skip_block = []
        current_layer_buffer = []
        
        # This list will store the line numbers of detected relative positioning commands
        relative_positioning_lines_detected = []

        current_layer = 0 # 'pre' layer is 0 and first printing layer is 1 (because thats how the UI shows it)
        layer_z = 0
        current_z = 0
        skip_reference_point = 0.0
        comments = []
        
        tracked_state = {
            "tool_change": [],  # e.g., ; CP TOOLCHANGE START \n.... OR a "nonmesh" block that contains a "^T\d+" operation
            
            ## this layer init is really just to get the "last z" value prior to the current layers "setup" and if its the same as the layer z then its the starting height
            ## still not sure how to do this right and its mostly a cura thing, but could be any slicer really...
            "layer_init": [],  # eg: ;MESH:NONMESH \n G0 F7200 X97.683 Y98.776 - a nonmesh block that has Z value (and perhaps NO TOOL opertionas - although perhaps it wont matter if a "tool change and a layer init" is insert twice...??)

            "bed_temp": None,
            
            "extrusion_mode": None, # is it currently in M82(abs)/M83(rel) ... if so then A) need to set this in resume, and B) if its currently IN absolute then need to insert last known Extrusion state
            "last_extrusion": 0.0,
            
            "fan_speed": None,

            "layer_height": 0.0,  # Default or derived from metadata
        }

        self._logger.info(f"Processing skipto: [{self._skip_mode_description(skip_mode)}] to [{target}] on file: {src_file_path}")

        target = self._convert_target(skip_mode, target)
        first_marker_index = None
        first_extrusion_found = False
        
        with open(src_file_path, "r") as file:
            lines = file.readlines()
            comparison_value = 0  # stores layer or z value for comparison to target
            skip_reference_point = 0  # stores actual value upon resumption of layer output (layer or z value)

            for line_count, line in enumerate(lines, start=1):
                # Detect Z height changes and layer shifts
                (
                    current_layer,
                    layer_z,
                    current_z,
                    layer_change_detected,
                    first_marker_index,
                    first_extrusion_found
                ) = self._detect_z_height_and_layers(
                    line,
                    current_layer,
                    layer_z,
                    current_z,
                    first_marker_index,
                    first_extrusion_found
                )
                
                if layer_change_detected:
                    skip_reference_point = self._evaluate_and_process_layer(
                        current_layer_buffer,
                        output_lines,
                        skip_block,
                        tracked_state,
                        current_layer-1,
                        current_z,
                        skip_mode,
                        target,
                        comparison_value,
                        skip_reference_point,
                        disable_z_homing,
                        start_print,
                        comments
                    )
                    current_layer_buffer = []  # Reset the layer buffer
                else:
                    if current_layer == 0:  # Handle the "init" or "setup" layer specifically
                        # Track M82 or M83 commands for extrusion mode in the init layer
                        if "M82" in line or "M83" in line:
                            self._track_print_state(line, tracked_state)
                    elif current_layer > 0: # only track and compare once we are past the "setup/header" info
                        comparison_value = current_layer if skip_mode == "L" else layer_z
                        if comparison_value < target:
                            self._track_print_state(line, tracked_state)
                        self._check_relative_positioning(relative_positioning_lines_detected, line, line_count)
                    
                current_layer_buffer.append(line)  # Add line to the current buffer

            # Handle the remaining buffer after the 'lines' loop finishes
            if current_layer_buffer:
                current_layer += 1
                skip_reference_point = self._evaluate_and_process_layer(
                    current_layer_buffer,
                    output_lines,
                    skip_block,
                    tracked_state,
                    current_layer,
                    current_z,
                    skip_mode,
                    target,
                    comparison_value,
                    skip_reference_point,
                    disable_z_homing,
                    start_print,
                    comments
                )

        # After processing all lines, handle any results
        if relative_positioning_lines_detected:
            comments.append(f"Relative positioning (G91) detected (lines: {relative_positioning_lines_detected}).")

        if skip_reference_point == 0:
            self._handle_skipping_failure(target, current_layer, current_z)
        else:
            new_file_path = self._output_lines_to_new_file(src_file_path, output_lines, skip_mode, target, comments)
            self._queue_file_for_printing(new_file_path, start_print)

    ########################################################################
    # Supporting functions
    ########################################################################

    def _track_print_state(self, line, tracked_state):
        """
        Tracks specific printer state information based on the provided line.
        
        Args:
            line (str): The line of G-code to parse.
            tracked_state (dict): The dictionary to store tracked state information.

        Returns:
            None: Updates the `tracked_state` dictionary in place.
        """
        # Static-like variables for block state
        if not hasattr(self, "inBlock"):
            self.inBlock = False
        if not hasattr(self, "temp_block"):
            self.temp_block = []
        

        # Check if currently in a block
        if self.inBlock:
            # Check if block end is detected - TODO/NOTE:possibly "any comment" if the start is a "nonmesh"?? 
            if re.search(r"^;(TIME|TYPE)|^; CP TOOLCHANGE END", line):  
                self.inBlock = False

                if line.startswith("; CP TOOLCHANGE END"):
                    self.temp_block.append(line)

                self._logger.debug(f"finish a block {self.temp_block}")

                # Check if the block is empty (only comments, no commands)
                if all(line.strip().startswith(";") for line in self.temp_block):
                    # If the block contains only comments, discard it and log a warning
                    self._logger.warning(f"Discarding empty block (all comments and no commands) {self.temp_block}")
                else:
                    # Identify the collected block
                    block_type = self._analyse_block(self.temp_block)
                    
                    if block_type == "TOOLCHANGE":
                        tracked_state["tool_change"] = self.temp_block
                    elif block_type == "LAYERINIT":
                        tracked_state["layer_init"] = self.temp_block
                    else:
                        self._logger.error(f"Unknown block type {self.block_type}")
                    
                self.temp_block = []  # Reset the block buffer
                
            else:
                self.temp_block.append(line)
        else:
            if re.search(r";MESH:NONMESH|; CP TOOLCHANGE START", line):  
                self.temp_block.append(line)
                self.inBlock = True
            else:
                # Process single line if not in a block
                command, _, comment = line.partition(";")
                
                # Track extrusion mode (absolute or relative)
                if "M82" in line or "M83" in command:  
                    tracked_state["extrusion_mode"] = line

                # Track last extrusion value
                extrusion_match = re.search(r"\bE(-?\d*\.?\d+)", line)  # Matches "E" followed by a number
                if extrusion_match:
                    tracked_state["last_extrusion"] = float(extrusion_match.group(1))
                    
                # Track bed temperature changes
                if "M140" in line or "M190" in command:  # Extrusion mode
                    tracked_state["bed_temp"] = line

                # Track fan speed
                if "M106" in command:  # Fan speed commands
                    tracked_state["fan_speed"] = line

                # Track layer height metadata (case-insensitive)
                layer_match = re.search(
                    r";LAYER[\s_-]?HEIGHT:\s*(\d+\.?\d*([eE][+-]?\d+)?)",  # Matches decimals and scientific notation
                    line,
                    re.IGNORECASE
                )
                if layer_match:
                    tracked_state["layer_height"] = float(layer_match.group(1))


    def _analyse_block(self, block):
        """
        Analyzes a block of G-code to determine its type.
        
        Args:
            block (list): A list of G-code lines representing a block.

        Returns:
            str: The type of the block ('TOOLCHANGE' or 'LAYERINIT').

        Raises:
            ValueError: If the block cannot be classified.
        """
        # Precompiled regex patterns
        tool_change_pattern = re.compile(r"^\s*(T\d+|; CP TOOLCHANGE START)", re.IGNORECASE)
        z_height_pattern = re.compile(r"^\s*G[01].*Z[-+]?\d*\.?\d+", re.IGNORECASE)

        # Check for tool change operation
        for line in block:
            if tool_change_pattern.search(line):
                return "TOOLCHANGE"

        # Check for Z-height change
        for line in block:
            if z_height_pattern.search(line):
                return "LAYERINIT"

        # Log exception if block type cannot be determined
        self._logger.error(f"Unable to classify block:\n{block}")
        raise ValueError("Block cannot be classified as TOOLCHANGE or LAYERINIT.")


    def _evaluate_and_process_layer(self, layer_buffer, output_lines, skip_block, tracked_state, layer_number, 
                                    current_z, skip_mode, target, comparison_value, skip_reference_point, 
                                    disable_z_homing, start_print_immediately, comments):
        # Debugging print statements for all parameters TODO: remove this
        self._logger.debug(
            f"Evaluating layer:\n"
            f"  layer_buffer_size={len(layer_buffer)}"
            f"  layer_number={layer_number},\n"
            f"  current_z={current_z},\n"
            f"  skip_mode={skip_mode},\n"
            f"  target={target},\n"
            f"  comparison_value={comparison_value},\n"
            f"  skip_reference_point={skip_reference_point},\n"
        )
        
        if layer_number == 0:  # initial (pre-layers) operations
            output_lines.extend(self._process_initialization_block(
                layer_buffer,        
                skip_mode,
                target,
                disable_z_homing,
                start_print_immediately
            ))
            # add a warning if we've finished the initialization layer but haven't seen any extrusion mode default
            if tracked_state["extrusion_mode"] is None:
                self._logger.warning("No extrusion mode default found in the first layer.")

        elif comparison_value >= target:  # threshold reached
            if skip_reference_point == 0.0:  # first layer to start, so add getting ready first
                output_lines.extend(self._prepare_resume_state(tracked_state, current_z))
                skip_reference_point = comparison_value
                self._logger.info(f"Found skipto {skip_mode}{skip_reference_point} - (first layer lines:{len(layer_buffer)}) - startswith:{layer_buffer[0]} ") 
                comments.append(f"REF {self._skip_mode_description(skip_mode)} - {skip_reference_point}")
                if True: # TODO: possibly make this configurable or user settable
                    output_lines.extend(skip_block)
                else:
                    output_lines.append(f"    ; SKIPPED LAYERS TO  {self._skip_mode_description(skip_mode)} - {skip_reference_point} - DETAIL EXCLUDED")
            
            output_lines.extend(layer_buffer)

        else:  # Skipped
            # Collect all comment lines and metadata, extract Z values, and calculate average Z
            layer_skip_output = []

            metadata_stopped = False
            # Define a pattern for lines to exclude
            exclusions_pattern = r"(M117|G92)"

            for line in layer_buffer:
                command, _, _ = line.partition(';')
                stripped_line = line.strip()
                # Skip lines matching the exclusions pattern
                if re.search(exclusions_pattern, stripped_line):
                    continue  # Skip this line as if it doesn't exist

                # Collect comments that start with ';' and stop at the first non-comment
                if stripped_line.startswith(';'):
                    # Replace "LAYER" with "<<SKIPPED>>LAYER" in the comment lines
                    line = re.sub(r"LAYER", "<<SKIPPED>>LAYER", line, flags=re.IGNORECASE)
                    layer_skip_output.append(line)
                else:
                    break  # Stop collecting metadata
                    
            # Construct the skip note with layer marker and metadata
            layer_skip_output.append(f"    ; SKIPLAYER ({layer_number}) \n")
            #optionally add gcode so the layer isn't invisible
            layer_skip_output.append("G4 P0  ; Dwell for 0 milliseconds - do nothing in skipped layer\n")

            # Append the skip note to output lines
            skip_block.extend(layer_skip_output)
        
        return skip_reference_point



    def _process_initialization_block(self, src_lines, skip_mode, target, disable_z_homing, start_print_immediately):
        """
        Processes the initialization block of G-code, modifying headers and filtering lines as needed.

        Args:
            src_lines (list): List of G-code lines to process.
            skip_mode (str): The skip mode target.
            target (str): The target value for skip mode.
            disable_z_homing (bool): Whether to disable Z homing.
            start_print_immediately (bool): Whether to start printing immediately.

        Returns:
            list: The processed G-code lines.
        """
        

        # Extract settings
        ignore_init_gcodes = (self._settings.get(["ignore_init_gcodes"]) or "").split("\n")

        output_lines = []
        header_lines = []
        header_done = False

        def filter_homing_command(line):
            """Filter and modify G28 commands if Z homing is disabled."""
            if re.match(r"^\s*G28", line):
                # Extract the command part and the comment part
                command_part, _, comment_part = line.partition(";")
                command_part = command_part.strip()

                # If Z homing is disabled, modify the command
                if disable_z_homing:
                    # Match G28 and any parameters (X, Y, Z) or none
                    match = re.match(r"^\s*G28(?:\s*([XYZ0\s]*))?", command_part)
                    if match:
                        axes = match.group(1)
                        
                        # If no axes are specified, use "G28 X Y"
                        if not axes.strip():
                            command_part = "G28 X Y"
                        else:
                            # Remove "Z" or "Z0" from the axes
                            axes = re.sub(r"Z0?\s*", "", axes)
                            axes = " ".join(axes.split())  # Normalize spaces between remaining axes
                            if not axes:
                                return ""  # If no axes remain after Z removal, return empty line
                            command_part = f"G28 {axes}"

                        # Append a comment indicating Z homing removal
                        return f"{command_part}   ;SKIPTO REMOVED Z HOMING    {comment_part}"

            # Return the line unchanged if it's not a G28 or doesn't match criteria
            return line

        def filter_general_commands(line):
            """Skip initial commands if there's a match on this line."""
            command_part, _, comment_part = line.partition(";")
            command_part = command_part.strip()
            comment_part = comment_part.strip() if comment_part else ""
        
            if any(re.match(pattern, command_part) for pattern in ignore_init_gcodes):
                exclusion_comment = f"    ;SKIPTO EXCLUSION -- {command_part}"
                if comment_part:
                    exclusion_comment += f" ; {comment_part}"
                return exclusion_comment
        
            return line

        filters = [filter_homing_command, filter_general_commands]

        has_header_entry = False
        has_header_finished = False

        for line in src_lines:
            stripped_line = line.strip()

            if not header_done:
                # Capture the first contiguous comment block as the header block
                if (stripped_line.startswith(";") or stripped_line == "" ) and  not has_header_finished:
                    header_lines.append(line)
                    if stripped_line.startswith(";"):
                        has_header_entry = True
                    if has_header_entry and stripped_line== "":
                        has_header_finished = True
                    continue
                else:
                    # Header block is complete, output it plus the "modified by" info
                    output_lines.extend(header_lines)
                    output_lines.append("\n")

                    # Insert the modified comment block
                    output_lines.append(";Modified by SKIPTO plugin\n")
                    output_lines.append(f"; Start printing at {self._skip_mode_description(skip_mode)} -> {target}\n")
                    output_lines.append("; Options:\n")
                    output_lines.append(f";   skip_mode : {skip_mode}\n")
                    output_lines.append(f";   target : {target}\n")
                    output_lines.append(f";   disable_z_homing : {disable_z_homing}\n")
                    output_lines.append(f";   start_print_immediately : {start_print_immediately}\n")
                    output_lines.append("; Settings:\n")
                    try:
                        default_setting_keys = self.get_settings_defaults().keys()
                        for key in default_setting_keys:
                            value = self._settings.get([key])
                            if isinstance(value, str) and "\n" in value:
                                value_lines = value.splitlines()
                                output_lines.append(f";   {key} ==\n")
                                for value_line in value_lines:
                                    output_lines.append(f";       {value_line}\n")
                            else:
                                output_lines.append(f";   {key} == {value}\n")
                    except Exception as e:
                        self._logger.error(f"ERROR: Failed to retrieve settings: {e}")
                        output_lines.append("; Failed to retrieve settings\n")
                    output_lines.append("\n")
                    header_done = True

            # Apply filters to the line
            for filter_func in filters:
                line = filter_func(line)
                if line is None:
                    break
            if line:
                if not line.endswith('\n'):
                    line += '\n'
                output_lines.append(line)

        return output_lines


    def _prepare_resume_state(self, tracked_state, current_z):
        z_offset = self._settings.get(["z_offset"]) or 2.0

        """Construct commands for preparing the printer to resume."""
        ready_lines = []
        ready_lines.append("\n")
        ready_lines.append("; PREP_START\n")
        ready_lines.append("    ; READY STATE - BUILT BY SKIPTO PLUGIN\n")
                

        ready_lines.append("\n")
        ready_lines.append(f";Offset platform Z for skipping layers \n")
        ready_lines.append(f"G0 Z{current_z + z_offset} \n")
        ready_lines.append("\n")
        
        
        if tracked_state.get("bed_temp"):
            ready_lines.append("; Restore bed temperature\n")
            ready_lines.append(f"{tracked_state['bed_temp']}\n")
            
        if tracked_state.get("fan_speed"):
            ready_lines.append(f"; Restore fan speed\n")
            ready_lines.append(f"{tracked_state['fan_speed']}\n")


        # Add lines from tool_change block if present
        tool_change_block = tracked_state.get("tool_change")
        if tool_change_block:
            ready_lines.append("; Tool change block\n")
            for line in tool_change_block:
                # Replace any Z value in the line with the updated Z value
                updated_line = re.sub(
                    r'\bZ([\d.]+)\b',  # Match Z followed by a number
                    lambda match: f"Z{current_z + z_offset}",  # Replace with the updated Z value
                    line
                )
                ready_lines.append(updated_line)  # Append the updated line
            ready_lines.append("\n")



        # Add lines from layer_init block if present - this must be last becasue of how some slicers are with the "last block" in teh previous layer
        layer_init_block = tracked_state.get("layer_init")
        if layer_init_block:
            ready_lines.extend(layer_init_block)  # Append all lines from the block


        # Append the extrusion_mode even if its redundant and then optional the extrusion state
        ready_lines.append(f"; Restore extrusion status due to absolute mode\n")
        extrusion_mode = tracked_state.get("extrusion_mode", "M82 ; SKIPTO default to relative extrusion mode")  # Default to M82 if not set, because this is the default for most printers, and some even default to this after tool changes, but hopefully most slicers explicitly set this...!?
        ready_lines.append(f"{extrusion_mode}\n")

        # Add extrusion state if the mode is currently absolute
        if extrusion_mode.strip().startswith("M82"):
            last_extrusion = tracked_state.get("last_extrusion", 0.0)  # Default to 0.0 if not available
            ready_lines.append(f"G92 E{last_extrusion}  ; SKIPTO extrusion initalization for absolute mode skipping\n")  # Reset extruder position using G92
            
 
        ready_lines.append("; PREP_END\n")
        ready_lines.append("\n")
        
        return ready_lines


    def _detect_z_height_and_layers(self, line, current_layer, layer_z, current_z, first_marker_index, first_extrusion_found):
        """
        Detects changes in Z height and layers.

        Args:
            line (str): The current G-code line.
            current_layer (int): The current layer number.
            current_z (float): The current Z height.

        Returns:
            tuple: The updated layer number, updated Z height, and whether a layer change was detected.
        """
        # Patterns to detect layer changes for various slicers
        layer_change_patterns = [
            r";\s*LAYER[_\-\:\s]*(\d+|CHANGE)",  # CURA, ideaMaker, Simplify3D, Prusa
            r";\s*(BEGIN|BEFORE)_LAYER_(OBJECT|CHANGE)",  # KISSlicer, Slic3r
        ]
        layer_change_detected = None
        
        if first_marker_index is None:
            for idx, pattern in enumerate(layer_change_patterns):  # Use enumerate to get the index
                if re.match(pattern, line, re.IGNORECASE):
                    first_marker_index = idx
                    layer_change_detected = True
                    break  # Stop after match
        else:
            # If the first marker index is set, only check that pattern
            if re.match(layer_change_patterns[first_marker_index], line, re.IGNORECASE):
                layer_change_detected = True
       
        if layer_change_detected:
            current_layer += 1
            self._logger.debug(f"found layer marker {current_layer} (Z actual:{current_z} layer:{layer_z}) - {line} ")
            first_extrusion_found = False

        # Detect Z height and store it as the "height" of this layer, stop storing it once extrusions start - assuming this is printing (may need to acocunt for tool operations or wipes)
        command,_,_ = line.strip().partition(';')
        if command:

            z_match = re.search(r"\s*Z(\d*\.?\d+)", command)
            
            # collect any Z values
            if z_match:
                current_z = float(z_match.group(1)) 

            if not first_extrusion_found:
                # - look for first extrusion value - Detect E-codes (postive only)
                e_match = re.search(r"\s*E(-?\d*\.?\d+)", command)
                if e_match:
                    new_e = float(e_match.group(1)) 
                    # if first_extrusion_found then lock in the z height for this layer
                    if new_e > 0.0:
                        first_extrusion_found = True
                        layer_z = current_z
                        self._logger.debug(f"layer z set {layer_z}")
                            
        return current_layer, layer_z, current_z, layer_change_detected, first_marker_index, first_extrusion_found 


    def _convert_target(self, skip_mode, target):
        """
        Converts the target value to the appropriate type (int for layers, float otherwise).
        
        Args:
            skip_mode (str): The skip mode ('L' or other).
            target (str): The target value to convert.

        Returns:
            int or float: The converted target value.
        """
        return int(target) if skip_mode == "L" else float(target)



    def _check_relative_positioning(self, relative_positioning_lines_detected, line, line_count):
        if re.match(r"\s*G91", line):  # Match G91 command indicating relative positioning
            relative_positioning_lines_detected.append(line_count)
            

    def _handle_skipping_failure(self, target, current_layer, current_z):
        self._logger.warning(
            f"Skipping failed: No valid layer or Z-height reached for target {target}. "
            f"Last detected layer: {current_layer}, Z-height: {current_z}. "
            "Check the input values or confirm the file format."
        )
        self._plugin_manager.send_plugin_message(self._identifier, {
            "type": "warning",
            "message": (
                f"Skipping to target={target} failed. "
                f"Last detected layer: {current_layer}, Z-height: {current_z}. "
                "Please check input and try again."
            )
        })
        
        
    def _queue_file_for_printing(self, new_file_path, start_print):
        self._printer.select_file(new_file_path, self._isSdCardFile(new_file_path), start_print)
        self._plugin_manager.send_plugin_message(self._identifier, {
            "type": "info",
            "message": f"{new_file_path} sent to printer... ({'and started' if start_print else 'but not started'})"
        })
    
            
    def _isSdCardFile(self, file_path):
        """
        Check if the given file path is on the SD card.
        
        The check is case-insensitive and normalized for cross-platform consistency.
        
        Returns:
            bool: True if the file path contains '/sdcard/', False otherwise.
        """
        # Normalize path for cross-platform consistency
        file_path = os.path.normpath(file_path)
        return 'sdcard' in file_path.lower()


    def _generate_new_file_path(self, src_file_path, mode_description, target_value, use_tempfile, temp_filename, appending_string):
        """
        Generate the file path where the modified GCODE will be saved.
        """
        if use_tempfile:
            # Ensure the temp file is always placed in the "local/root"
            new_file_path = self._file_manager.path_on_disk(octoprint.filemanager.FileDestinations.LOCAL, temp_filename)
        else:
            # Remove trailing .gcode (case-insensitive)
            src_file_base, _ = os.path.splitext(src_file_path)
            
            # Replace placeholders in the suffix
            suffix = appending_string
            suffix = re.sub(r"{mode}", str(mode_description), suffix)  # Replace {mode} if it exists
            suffix = re.sub(r"{value}", str(target_value), suffix)  # Replace {value} if it exists
            
            # Ensure that the suffix isn't empty and is properly concatenated
            if suffix:
                new_file_path = src_file_base + suffix
            else:
                new_file_path = src_file_base + ".gcode"  # Ensure .gcode extension

        # Ensure the filename ends with .gcode (even if suffix was added or temp filename used)
        if not new_file_path.lower().endswith(".gcode"):
            new_file_path += ".gcode"

        return new_file_path


    def _output_lines_to_new_file(self, src_file_path, lines, mode_description, target_value, comments):
        """
        Writes modified GCODE lines to a new or temporary file based on settings.
        """
        # Retrieve settings values with proper keys
        use_tempfile = self._settings.get(["use_tempfile"])
        temp_filename = self._settings.get(["temp_filename"])
        appending_string = self._settings.get(["appending_string"])


        # Generate the new file path using the helper function
        new_file_path = self._generate_new_file_path(src_file_path, mode_description, target_value, use_tempfile, temp_filename, appending_string)

        # Write the modified GCODE to a new or temporary file
        try:
            self._logger.info(
                f"Skip {mode_description} to {target_value} complete. Modified GCODE will save to {new_file_path}. {comments}"
            )

            with open(new_file_path, "w") as file:
                file.writelines(lines)

            return new_file_path
        except Exception as e:
            self._logger.error(f"Error writing GCODE to file: {str(e)}")
            raise


    ########################################################################
        

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
