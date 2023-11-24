
// Get the button element
const saveButton = document.getElementById('save-button');

// Add a click event listener to the button
saveButton.addEventListener('click', () => {
    // Get the value of the input field
    const baseUrl = document.getElementById('untube_url').value;
    
    // Save the value to local storage
    browser.storage.local.set({ untube_url: baseUrl }, () => {
        // Notify the user that the settings have been saved
        console.log('Settings saved!');
    });
});

// Fill the input field with the saved settings
browser.storage.local.get('untube_url', (result) => {
    if (result.untube_url) {
        document.getElementById('untube_url').value = result.untube_url;
    }
});
