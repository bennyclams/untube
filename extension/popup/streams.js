
let tableBody = document.getElementById("tableBody")
function createTableRow(data) {
    browser.storage.local.get("untube_url").then((result) => {
        let row = document.createElement("tr")
        let link = document.createElement("a")
        let linkCell = document.createElement("td")
        let linkText = document.createTextNode(data.title)
        let full_url = result.untube_url + "/info/video/?yt=no"
        let dl_url = new URL(full_url)
        dl_url.searchParams.append("v", data.full_url)
        dl_url.searchParams.append("title", data.title)
        link.appendChild(linkText)
        link.href = dl_url.href
        link.target = "_blank"
        linkCell.appendChild(link)
        row.appendChild(linkCell)
        tableBody.appendChild(row)
    })
}

function buildTable() {
    let storedUrls = browser.storage.local.get("urls")
    storedUrls.then((result) => {
        if (result.urls) {
            result.urls.reverse()
            for (let i = 0; i < result.urls.length; i++) {
                createTableRow(result.urls[i])
            }
        }
    })
}

buildTable()