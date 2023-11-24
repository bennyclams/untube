// let filter = ["stream.mux.com"]
let urlFilter = ["*://stream.mux.com/*"]

function interceptRequest(details) {
    console.log("intercepted request " + details.url)
    browser.tabs.get(details.tabId).then((tab) => {
        let url = new URL(details.url)
        let storedUrls = browser.storage.local.get("urls")
        let data = {
            full_url: details.url,
            host: url.host,
            path: url.pathname,
            query: url.search,
            title: tab.title,
            origin: details.originUrl,
        }
        storedUrls.then((result) => {
            if (result["urls"]) {
                let urls = result["urls"]
                for (let i = 0; i < urls.length; i++) {
                    if (urls[i].full_url == details.url) {
                        return
                    }
                }
                urls.push(data)
                browser.storage.local.set({urls: urls})
            } else {
                browser.storage.local.set({urls: [data]})
            }
        })
    })
}

browser.webRequest.onBeforeSendHeaders.addListener(interceptRequest, {urls: urlFilter}, ["requestHeaders"])