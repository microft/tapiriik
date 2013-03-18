from lxml import etree
from pytz import UTC
import copy
import dateutil.parser
from datetime import datetime
from .interchange import WaypointType, Activity, Waypoint, Location


class GPXIO:
    Namespaces = {
        None: "http://www.topografix.com/GPX/1/1",
        "gpxtpx": "http://www.garmin.com/xmlschemas/TrackPointExtension/v1",
        "gpxext": "http://www.garmin.com/xmlschemas/GpxExtensions/v3"
    }

    def Parse(gpxString):
        ns = copy.deepcopy(GPXIO.Namespaces)
        ns["gpx"] = ns[None]
        del ns[None]
        act = Activity()
        act.Distance = None

        root = etree.fromstring(gpxString.encode("UTF-8"))
        xmeta = root.find("gpx:metadata", namespaces=ns)
        if xmeta is not None:
            xname = xmeta.find("gpx:name", namespaces=ns)
            if xname is not None:
                act.Name = xname.text
        xtrk = root.find("gpx:trk", namespaces=ns)

        xtrksegs = xtrk.findall("gpx:trkseg", namespaces=ns)
        startTime = None
        endTime = None

        beginSeg = False
        for xtrkseg in xtrksegs:
            beginSeg = True
            for xtrkpt in xtrkseg.findall("gpx:trkpt", namespaces=ns):
                wp = Waypoint()
                if len(act.Waypoints) == 0:
                    wp.Type = WaypointType.Start
                elif beginSeg:
                    wp.Type = WaypointType.Resume
                beginSeg = False

                wp.Timestamp = dateutil.parser.parse(xtrkpt.find("gpx:time", namespaces=ns).text)
                if startTime is None or wp.Timestamp < startTime:
                    startTime = wp.Timestamp
                if endTime is None or wp.Timestamp > endTime:
                    endTime = wp.Timestamp

                wp.Location = Location(float(xtrkpt.attrib["lat"]), float(xtrkpt.attrib["lon"]), None)
                eleEl = xtrkpt.find("gpx:ele", namespaces=ns)
                if eleEl is not None:
                    wp.Location.Altitude = float(eleEl.text)
                extEl = xtrkpt.find("gpx:extensions", namespaces=ns)
                if extEl is not None:
                    gpxtpxExtEl = extEl.find("gpxtpx:TrackPointExtension", namespaces=ns)
                    if gpxtpxExtEl is not None:
                        hrEl = gpxtpxExtEl.find("gpxtpx:hr", namespaces=ns)
                        if hrEl is not None:
                            wp.HR = int(hrEl.text)
                        cadEl = gpxtpxExtEl.find("gpxtpx:cad", namespaces=ns)
                        if cadEl is not None:
                            wp.Cadence = int(cadEl.text)
                        tempEl = gpxtpxExtEl.find("gpxtpx:atemp", namespaces=ns)
                        if tempEl is not None:
                            wp.Temp = float(tempEl.text)
                act.Waypoints.append(wp)


            act.Waypoints[len(act.Waypoints)-1].Type = WaypointType.Pause

        act.Waypoints[len(act.Waypoints)-1].Type = WaypointType.End
        act.TZ = act.Waypoints[0].Timestamp.tzinfo
        act.StartTime = startTime
        act.EndTime = endTime
        act.CalculateUID()
        return act


    def Dump(activity):
        GPXTPX = "{" + GPXIO.Namespaces["gpxtpx"] + "}"
        root = etree.Element("gpx", nsmap=GPXIO.Namespaces)
        root.attrib["creator"] = "tapiriik-sync"
        meta = etree.SubElement(root, "metadata")
        trk = etree.SubElement(root, "trk")

        if activity.Name is not None:
            etree.SubElement(meta, "name").text = activity.Name
            etree.SubElement(trk, "name").text = activity.Name

        trkseg = etree.SubElement(trk, "trkseg")
        inPause = False
        for wp in activity.Waypoints:
            if wp.Type == WaypointType.Pause:
                if inPause:
                    raise ValueError("Multiple consecutive pause waypoints - invalid GPX / dropped points will result")
                inPause = True
            if inPause and (wp.Type == WaypointType.Regular or wp.Type == WaypointType.Resume or wp.Type == WaypointType.End):
                trkseg = etree.SubElement(trk, "trkseg")
                inPause = False
            trkpt = etree.SubElement(trkseg, "trkpt")
            if wp.Timestamp.tzinfo is None:
                raise ValueError("GPX export requires TZ info")
            etree.SubElement(trkpt, "time").text = wp.Timestamp.astimezone(UTC).isoformat()
            trkpt.attrib["lat"] = str(wp.Location.Latitude)
            trkpt.attrib["lon"] = str(wp.Location.Longitude)
            if wp.Location.Altitude is not None:
                etree.SubElement(trkpt, "ele").text = str(wp.Location.Altitude)
            if wp.HR is not None or wp.Cadence is not None or wp.Temp is not None or wp.Calories is not None or wp.Power is not None:
                exts = etree.SubElement(trkpt, "extensions")
                gpxtpxexts = etree.SubElement(exts, GPXTPX + "TrackPointExtension")
                if wp.HR is not None:
                    etree.SubElement(gpxtpxexts, GPXTPX + "hr").text = str(int(wp.HR))
                if wp.Cadence is not None:
                    etree.SubElement(gpxtpxexts, GPXTPX + "cad").text = str(int(wp.Cadence))
                if wp.Temp is not None:
                    etree.SubElement(gpxtpxexts, GPXTPX + "atemp").text = str(wp.Temp)

        return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8").decode("UTF-8")