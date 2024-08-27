# OctoPrint-SkipTo

Adds buttons to the UI to allow the user to start/restart the print while skipping movement and extrustion processes in gcode.
Effectively allowing to start/restart a print from a specifc layer or z-height without having to muck around wiht the GCODE file directly. If everythings working you may never want to use it, however when you need it...

Basically choose a file, press the button, choose a Z or Layer# to "goto" and it shoudl process the file, keeping the "temp and init" stuff, but removing all the movement and extrusion related stuff, up until the layer/height in question, and then it should resume everything "as is" from there.
it then saves all this (either in a temp file, or a copy with a suffix appended) and loads that file to print immediately.

I hope you find it useful!

## Setup

Install via the bundled [Plugin Manager](https://docs.octoprint.org/en/master/bundledplugins/pluginmanager.html)
or manually using this URL:

    https://github.com/awe-source/OctoPrint-SkipTo/archive/master.zip

**TODO:** Describe how to install your plugin, if more needs to be done than just installing it via pip or through
the plugin manager.

## Configuration

Currently there's just three settings.
"temp file name", "appending string" and a toggle between the two...
Essentially, do you want to use a single file that is always the same name eg: "my_temp_layer_restart_file.gcode" or do you want each "skip" to be more detailed like "my fiddly model that I have to keep restarting by layer at layer40.gcode"
Hopefully its self explanatory... otherwise let us know!
