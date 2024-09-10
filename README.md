# OctoPrint-SkipTo

The **OctoPrint-SkipTo** plugin adds buttons to the UI to allow users to start/restart a print while skipping specific movement and extrusion processes in the GCODE. This feature allows you to resume prints from a specific layer or Z-height without the need to manually edit the GCODE file. When things go wrong mid-print or you need to restart from a specific point, SkipTo simplifies the process.

Essentially, you choose a file, press the button, select a Z-height or Layer number to "skip to," and the plugin processes the file. It retains the "temperature and initialization" commands but removes all the movement and extrusion commands up to the specified layer or height, then resumes the print "as is" from that point onward. The modified GCODE is saved as a temporary file or with an appended suffix and can be printed immediately.

We hope you find it useful!

## New Features & Enhancements

### 1. **Improved Command Filtering**
   - Skip logic now correctly filters out movement commands (e.g., `G1`, `G2`) before the print start, but retains critical positioning commands (`G20`, `G21`, `G90`, `G91`).
   - Specific GCODE positioning commands like `G90` (absolute positioning) and `G91` (relative positioning) are preserved to ensure print consistency.

### 2. **Warnings for Relative Positioning (`G91`)**
   - The plugin now detects and logs a warning when `G91` (relative positioning) is encountered. This informs users that relative positioning may affect the skip functionality, helping to avoid unexpected behavior during print restarts.

### 3. **Z-Height Handling Improvements**
   - Improved detection of Z-height changes within GCODE, ensuring the correct height is set when resuming from the specified layer or height.

### 4. **Custom Homing Commands**
   - Users can now configure whether to perform full homing or partial homing (e.g., X and Y only) after skipping to the desired layer or height. This allows for greater control when resuming prints.

### 5. **Z-Offset Configuration**
   - A customizable Z-offset can now be applied when resuming a print after skipping layers or Z-heights, ensuring smoother transitions during restart.

### 6. **File Naming Customization**
   - As before, the plugin allows you to choose between using a single temporary file (e.g., `my_temp_layer_restart_file.gcode`) or more detailed file names that reflect the layer or Z-height skipped to (e.g., `my_fiddly_model_layer40_restart.gcode`).

---

## Setup

Install via the bundled [Plugin Manager](https://docs.octoprint.org/en/master/bundledplugins/pluginmanager.html)
or manually using this URL:

```
https://github.com/awe-source/OctoPrint-SkipTo/archive/master.zip
```

## Configuration

In the settings menu, you can configure the following options:
- **Temporary File Name**: Choose a default name for the modified GCODE file (e.g., `my_temp_layer_restart_file.gcode`).
- **Appended Suffix**: Alternatively, enable detailed file names that include the skipped layer or Z-height, for example, `my_model_layer40_restart.gcode`.
- **Z-Offset**: Specify an optional Z-offset to apply when resuming a print after skipping layers or Z-heights.
- **Partial Homing**: Configure whether to perform full homing (`G28`) or just home the X and Y axes (`G28 X Y`) after skipping.

These settings help you tailor the plugin to your needs, whether you want to keep things simple with a single temp file or prefer a more detailed naming structure for each skip operation.
