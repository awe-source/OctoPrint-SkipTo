# OctoPrint-SkipTo

Adds buttons to the UI to allow the user to start/restart the print while skippint ALL movement processes in gcode.
Effectively allowing to start/restart a print from a specifc layer without having to muck around wiht the GCODE file directly. If everythings working you may never want to use it, however when you need it...

## Setup

Install via the bundled [Plugin Manager](https://docs.octoprint.org/en/master/bundledplugins/pluginmanager.html)
or manually using this URL:

    https://github.com/awe-source/OctoPrint-SkipTo/archive/master.zip

**TODO:** Describe how to install your plugin, if more needs to be done than just installing it via pip or through
the plugin manager.

## Configuration

Currently there's just three settings.
Do you want to use a single file that is always the same name eg: "my_temp_layer_restart_file.gcode" or do you want each "skip" to be more detailed like "my fiddly model that I have to keep restarting by layer at layer40.gcode"
Hopefully its self explanatory... otherwise let us know!
