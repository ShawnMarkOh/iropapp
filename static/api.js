async function getHubs() {
    const resp = await fetch('/api/hubs');
    const hubs = await resp.json();
    return hubs;
}

async function fetchGroundStops() {
    let res = await fetch('/api/groundstops');
    return await res.json();
}

async function fetchGroundDelays() {
    let res = await fetch('/api/grounddelays');
    return await res.json();
}

async function fetchWeather(iata) {
  let url = '/api/weather/' + iata;
  let dateMatch = window.location.search.match(/[?&]date=([0-9]{4}-[0-9]{2}-[0-9]{2})/);
  if (dateMatch) {
    url += '?date=' + dateMatch[1];
  }
  let res = await fetch(url);
  return await res.json();
}

async function fetchSnapshots(iata, date) {
    let url = `/api/hourly-snapshots/${iata}/${date}`;
    let res = await fetch(url);
    return await res.json();
}
