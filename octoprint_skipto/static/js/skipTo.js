/*
 * View model for OctoPrint-skipTo
 *
 * Author: awesrc
 * License: AGPLv3
 */

$(function () {
    // Define the skipToViewModel
    function skipToViewModel(parameters) {
        var self = this;

        // Assign the injected parameters
        self.settingsViewModel = parameters[0];

        // Observable values to bind to

        self.layerCount = ko.observable(0); // Current layer count
        self.zValue = ko.observable(0); // Current Z value

        self.use_tempfile = ko.observable(0);
        self.temp_filename = ko.observable("notset");
        self.appending_string = ko.observable("notset");

        // Function to handle dialog open and button click
        self.openSkipLayersDialog = function (fileinfo) {
            // Update file name and open dialog
            $("#skip-layers-dialog input[id='skip_filepath']").val("/" + decodeURIComponent(fileinfo.origin) + "/" + decodeURIComponent(fileinfo.path));
            $("#skip-layers-dialog").modal("show");
        };

        // Handle skip layers dialog submission
        self.processSkipLayers = function () {
            var filepath = $("#skip-layers-dialog input[id='skip_filepath']").val();
            var layer = $("#skip_layer").val();
            var z = $("#skip_z-height").val();
            var start_print = $("#start_print").is(":checked");
            var disable_z_homing = $("#skip_z_homing").is(":checked");

            OctoPrint.post(
                "plugin/SkipTo/skip_to",
                { filepath: filepath, layer: layer, z: z, start_print: start_print, disable_z_homing: disable_z_homing },
                function (response) {
                    if (response.success) {
                        console.log("Successfully processed skipped layers.");
                    } else {
                        console.error("Failed to skip layers:", response.message || "No message provided.");
                    }
                },
                function (jqXHR, textStatus, errorThrown) {
                    var errorMessage = "Error processing skip layers";
                    if (jqXHR.responseJSON && jqXHR.responseJSON.message) {
                        errorMessage = jqXHR.responseJSON.message;
                    } else if (jqXHR.responseText) {
                        errorMessage = jqXHR.responseText;
                    }
                    console.error(`${errorMessage}. Status: ${textStatus}. Error: ${errorThrown}`);
                }
            );
        };

        // Function to add skip button to file entries
        self.addButton = function () {
            $('#files .entry.machinecode .btn-group').each(function () {
                var buttonGroup = $(this);
                // only add if not already present
                if (buttonGroup.find('.skipTo-button').length === 0) {
                    var newButtonDiv = $('<div>')
                        .addClass('btn btn-mini skipTo-button')
                        .attr('title', 'Skip to Layer')
                        .attr('aria-label', 'Skip to Layer')
                        .attr('role', 'link')
                        .click(function () {
                            fileinfo = self.extractFileInfo($(this));
                            self.openSkipLayersDialog(fileinfo);
                        });

                    newButtonDiv.append($('<i>').addClass('fas fa-forward'));
                    buttonGroup.append(newButtonDiv);
                }
            });
        };

        self.extractFileInfo = function (referenceItem) {
            var url = referenceItem.parent().find('.btn.btn-mini[href]').attr("href")

            if (!url) {
                console.error('URL not found');
                return null;
            }

            // Create a URL object to parse the URL
            const urlObj = new URL(url, window.location.origin); // Provide the base URL for relative URLs

            // Extract the pathname from the URL
            const pathname = urlObj.pathname;

            // Split the pathname to get the components
            const pathParts = pathname.split('/').filter(part => part);

            let d = pathParts.shift();
            let f = pathParts.shift();
            if (d !== "downloads" && f !== "files" && pathParts.length == 0) {
                console.error('Unexpected or invalid path format');
                return null;
            }

            // Extract name, origin, and path from the split parts
            const origin = pathParts.shift();
            const name = pathParts[pathParts.length - 1];
            const path = pathParts.join('/'); // Join the remaining parts as path

            // Create the result object
            return {
                name: name,
                origin: origin,
                path: path
            };
        }

        self.getActiveFileInfo = function () {
            return OctoPrint.get("api/job")
                .then(function (data) {
                    return data.job.file;
                })
                .fail(function () {
                    console.error("Failed to get current job information");
                });
        };

        // Update button state based on the printing state
        self.updateButtonsState = function () {
            var button = $("#state-skip-layers-button");
            //if the #print_job button is disabled then so am I
            var jpbtn = $("#job_print");
            button.prop("disabled", jpbtn.prop("disabled"));

            var filebuttons = $("#files .skipTo-button");
            //if the #prev button is disabled then so am I
            $(filebuttons).each(function () {
                var ffbtn = $(this);
                var prevPntBtn = ffbtn.parent().find(".btn-mini[title='Load and Print']");

                // Check if the previous button has the "disabled" class
                if (prevPntBtn.hasClass("disabled")) {
                    ffbtn.addClass("disabled"); // Add the "disabled" class if the print button is disabled
                } else {
                    ffbtn.removeClass("disabled"); // Remove the "disabled" class if the print button is enabled
                }

            });

        };

        // Function to check if the start button should be enabled
        self.checkStartButtonState = function () {
            var layerValue = parseInt($("#skip_layer").val(), 10);
            var zValue = parseFloat($("#skip_z-height").val());
        
            if ((Number.isInteger(layerValue) && layerValue > 0) || (!isNaN(zValue) && zValue > 0)) {
                $("#start-button").prop("disabled", false);
            } else {
                $("#start-button").prop("disabled", true);
            }
        };
        

        // Initialize modal input fields and set up event listeners
        self.initModal = function () {
            $("#skip-layers-dialog input[name='skip_file']").val("");//??
            $("#skip_layer").val("");
            $("#skip_z-height").val("");
            $("#start_print").prop("checked", false);
            $("#skip_z_homing").prop("checked", true);

            $("#start-button").prop("disabled", true);

            // Event listeners for input changes
            $("#skip_layer").on("input", self.checkStartButtonState);
            $("#skip_z-height").on("input", self.checkStartButtonState);
        };

        // Relocate state info to the end of the STATE accordion
        self.setupUI = function () {

            $("#gen_plugin_skipTo").appendTo("#state .accordion-inner");

            //wire up the events
            $("#state-skip-layers-button").on("click", function () {
                self.getActiveFileInfo().done(function (fileinfo) {
                    if (fileinfo) {
                        // set the current layer in the dialog if this button is pressed
                        // just as a convenience for the user
                        $("#skip_layer").val(self.layerCount());

                        self.openSkipLayersDialog(fileinfo);
                    } else {
                        console.error("No file name available to skip layers.");
                    }
                });
            });

            // Add functionality to modal dialog buttons
            //trigger the file processing and close the dialog
            $("#start-button").on("click", function () {
                // Handle start action
                self.processSkipLayers();

                $("#skip-layers-dialog").modal("hide");
                self.initModal();
            });
            // clear and hide the dialog
            $(".cancel-operation").on("click", function () {
                $("#skip-layers-dialog").modal("hide");
                self.initModal();
            });

            setInterval(() => {
                self.addButton();
                self.updateButtonsState();
            }, 1500); // Continuously poll and add buttons if needed

            self.initModal();
        };

        self.onDataUpdaterPluginMessage = function (plugin, data) {
            if (plugin !== "SkipTo") {
                return;
            }

            if (data.status) {
                // Update the displayed values based on received data
                if (data.status.layerCount !== undefined) {
                    self.layerCount(data.status.layerCount);
                }
                if (data.status.zValue !== undefined) {
                    self.zValue(data.status.zValue);
                }
            }
            
            // Display the message as a notification
            if (data.message) {
                new PNotify({
                    title: 'SKIPTO Plugin',
                    text: data.message,
                    type: data.type,
                    hide: false,
                    buttons: {
                        sticker: false
                    }
                });
            }
        };

        self.onStartupComplete = function () {
            self.setupUI();
        };
    }

    /* view model class, parameters for constructor, container to bind to
     * Please see http://docs.octoprint.org/en/master/plugins/viewmodels.html#registering-custom-viewmodels for more details
     * and a full list of the available options.
     */
    OCTOPRINT_VIEWMODELS.push({
        construct: skipToViewModel,
        dependencies: ["settingsViewModel"],
        elements: ["#gen_plugin_skipTo"]
    });
});
