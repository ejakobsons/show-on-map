function inputChanged() {
  if (document.getElementById("urlInput").value == "") {
    document.getElementById("extractButton").disabled = true;
  } else {
    document.getElementById("extractButton").disabled = false;
    document.getElementById("status").innerHTML = "";
  }
}

async function verify() {
  if (document.getElementById("urlInput").value == "") {
    document.getElementById("status").innerHTML = "Please enter a URL!";
    return;
  } else {
    await findLocations();
  }
}

var map;
var pushpins = [];
var pin_layer;
var pages = 0;

function startMap() {
  map = new Microsoft.Maps.Map(document.getElementById("map"), {});
  pin_layer = new Microsoft.Maps.Layer();
}

// Initiate location extractiona
async function findLocations() {
  document.getElementById("extractButton").disabled = true;
  document.getElementById("status").innerHTML = "Loading...";
  document.getElementById("mapImage").style.display = "none";
  // empty the list of addresses
  document.getElementById("address_list").innerHTML = "";
  pushpins = [];
  pages = 0;
  // start the extraction
  var nextUrl = document.getElementById("urlInput").value;
  // keep loading up to 10 pages
  while (nextUrl && pages < 10) {
    if (pages > 0) {
      document.getElementById("status").innerHTML += ", loading next page...";
    }
    nextUrl = await extractAddresses(nextUrl);
  }
}

async function extractAddresses(url) {
  try {
    // send a request to the server
    const response = await fetch(`/get_locations?url=${url}`, {
      method: "GET",
    });
    const data = await response.json();
    document.getElementById("address_list").innerHTML +=
      data.locations
        .map((loc, index) => `${loc.title}: ${data.addresses[index]}`)
        .join("<br>") + "<br>";
    // create the map on the first received locations
    if (!map) {
      startMap();
    }
    if (data.locations.length > 0) {
      pages += 1;
      updateMap(data.locations);
    }
    return data.nextUrl;
  } catch (error) {
    document.getElementById("status").innerHTML = "Something went wrong!";
  }
}

// Add new locations to the map
function updateMap(locations) {
  pushpins.push(
    ...locations.map(
      (location) =>
        new Microsoft.Maps.Pushpin(
          new Microsoft.Maps.Location(location.lat, location.lon),
          { title: location.title }
        )
    )
  );
  var status = `Found ${pushpins.length} location`;
  if (pushpins.length > 1) {
    status += "s";
  }
  if (pages > 1) {
    status += ` on ${pages} pages`;
  }
  document.getElementById("status").innerHTML = status;

  pin_layer.clear();
  pin_layer.add(pushpins);
  map.layers.insert(pin_layer);

  // Calculate bounding box to include all pushpins
  var bounds = Microsoft.Maps.LocationRect.fromLocations(
    pushpins.map(function (pin) {
      return pin.getLocation();
    })
  );

  // Set center and zoom based on the bounding box
  map.setView({ bounds: bounds });
}
