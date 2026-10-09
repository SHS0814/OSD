package kr.ac.cbnu.campusshade

import android.app.DatePickerDialog
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.widget.ArrayAdapter
import android.widget.AutoCompleteTextView
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.graphics.ColorUtils
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import kr.ac.cbnu.campusshade.databinding.ActivityMainBinding
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import org.json.JSONObject
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.Style
import org.maplibre.android.style.expressions.Expression.coalesce
import org.maplibre.android.style.expressions.Expression.color
import org.maplibre.android.style.expressions.Expression.eq
import org.maplibre.android.style.expressions.Expression.get
import org.maplibre.android.style.expressions.Expression.literal
import org.maplibre.android.style.expressions.Expression.match
import org.maplibre.android.style.expressions.Expression.stop
import org.maplibre.android.style.expressions.Expression.switchCase
import org.maplibre.android.style.expressions.Expression.typeOf
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.FillExtrusionLayer
import org.maplibre.android.style.layers.FillLayer
import org.maplibre.android.style.layers.Layer
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.layers.PropertyFactory.circleColor
import org.maplibre.android.style.layers.PropertyFactory.circlePitchAlignment
import org.maplibre.android.style.layers.PropertyFactory.circleRadius
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeColor
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeWidth
import org.maplibre.android.style.layers.PropertyFactory.fillColor
import org.maplibre.android.style.layers.PropertyFactory.fillExtrusionBase
import org.maplibre.android.style.layers.PropertyFactory.fillExtrusionColor
import org.maplibre.android.style.layers.PropertyFactory.fillExtrusionHeight
import org.maplibre.android.style.layers.PropertyFactory.fillExtrusionOpacity
import org.maplibre.android.style.layers.PropertyFactory.fillOpacity
import org.maplibre.android.style.layers.PropertyFactory.lineCap
import org.maplibre.android.style.layers.PropertyFactory.lineColor
import org.maplibre.android.style.layers.PropertyFactory.lineJoin
import org.maplibre.android.style.layers.PropertyFactory.lineWidth
import org.maplibre.android.style.layers.PropertyFactory.rasterOpacity
import org.maplibre.android.style.layers.PropertyFactory.rasterResampling
import org.maplibre.android.style.layers.PropertyFactory.textAnchor
import org.maplibre.android.style.layers.PropertyFactory.textColor
import org.maplibre.android.style.layers.PropertyFactory.textField
import org.maplibre.android.style.layers.PropertyFactory.textFont
import org.maplibre.android.style.layers.PropertyFactory.textHaloColor
import org.maplibre.android.style.layers.PropertyFactory.textHaloWidth
import org.maplibre.android.style.layers.PropertyFactory.textOffset
import org.maplibre.android.style.layers.PropertyFactory.textSize
import org.maplibre.android.style.layers.PropertyFactory.visibility
import org.maplibre.android.style.layers.RasterLayer
import org.maplibre.android.style.layers.SymbolLayer
import org.maplibre.android.style.sources.GeoJsonSource
import org.maplibre.android.style.sources.ImageSource
import org.maplibre.android.style.sources.RasterSource
import org.maplibre.android.style.sources.TileSet
import java.io.IOException
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private val client = OkHttpClient()
    private val handler = Handler(Looper.getMainLooper())
    private var map: MapLibreMap? = null
    private var mapStyle: Style? = null
    private var shadowCall: Call? = null
    private var microclimateCall: Call? = null
    private var selectedMinutes = 14 * 60
    private var is3d = true
    private var showHeatmap = true
    private var showSatellite = true

    // 길찾기: 출발지·도착지(건물 또는 지도에서 길게 누른 곳)와 건물 목록
    private var places: List<Place> = emptyList()
    private var routeStart: Place? = null
    private var routeEnd: Place? = null
    private var routeCall: Call? = null

    // Shadows and felt temperature are shown for today when the server keeps its
    // weather current (API허브), otherwise for the last fully observed day.
    private var dataDate: LocalDate = LocalDate.now(SEOUL_ZONE)
    // The date "현재 시각" returns to, and the range the date picker allows;
    // both come from /api/weather/period.
    private var defaultDate: LocalDate = dataDate
    private var firstDate: LocalDate? = null
    private var latestObservation: LocalDateTime? = null
    private val debounceRequest = Runnable { requestForSelectedTime() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        MapLibre.getInstance(this)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        // Android 15+ draws apps edge to edge; keep the title and controls clear of
        // the status and navigation bars.
        ViewCompat.setOnApplyWindowInsetsListener(binding.root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }
        binding.mapView.onCreate(savedInstanceState)

        setToCurrentTime(requestImmediately = false)
        configureControls()
        buildLegend()
        updateDataDateLabel()
        binding.mapView.getMapAsync { mapLibreMap ->
            map = mapLibreMap
            mapLibreMap.cameraPosition = CameraPosition.Builder()
                .target(CAMPUS_CENTER)
                .zoom(16.2)
                .tilt(MapStyle.TILT_3D)
                .build()
            mapLibreMap.addOnMapLongClickListener { point -> pickRoutePoint(point); true }
            mapLibreMap.setStyle(Style.Builder().fromUri(MapStyle.BASE_STYLE_URL)) { style ->
                mapStyle = style
                installDataLayers(style)
                requestBuildings()
                requestSensors()
                requestDataDateThenRefresh()
            }
        }
    }

    private fun configureControls() {
        binding.timeSlider.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                selectedMinutes = START_MINUTES + progress
                updateTimeLabel()
                if (fromUser) {
                    handler.removeCallbacks(debounceRequest)
                    handler.postDelayed(debounceRequest, 400)
                }
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) = Unit
            override fun onStopTrackingTouch(seekBar: SeekBar?) = Unit
        })
        binding.nowButton.setOnClickListener {
            dataDate = defaultDate
            updateDataDateLabel()
            setToCurrentTime(requestImmediately = true)
        }
        binding.dateButton.setOnClickListener { pickDate() }
        binding.viewModeButton.setOnClickListener { toggleViewMode() }
        binding.layerModeButton.setOnClickListener { toggleLayerMode() }
        binding.baseMapButton.setOnClickListener { toggleBaseMap() }
        binding.routeButton.setOnClickListener { showRouteDialog() }
        binding.clearRouteButton.setOnClickListener { clearRoute() }
        updateViewModeButton()
        updateLayerMode()
    }

    private fun toggleViewMode() {
        is3d = !is3d
        val tilt = if (is3d) MapStyle.TILT_3D else 0.0
        map?.animateCamera(CameraUpdateFactory.tiltTo(tilt), 600)
        updateViewModeButton()
    }

    private fun updateViewModeButton() {
        binding.viewModeButton.setText(if (is3d) R.string.view_2d else R.string.view_3d)
    }

    // The heatmap already accounts for shade, so it replaces the shadow layer
    // instead of being drawn on top of it.
    private fun toggleLayerMode() {
        showHeatmap = !showHeatmap
        updateLayerMode()
        requestForSelectedTime()
    }

    private fun updateLayerMode() {
        binding.layerModeButton.setText(if (showHeatmap) R.string.show_shadows else R.string.show_heatmap)
        binding.legend.visibility = if (showHeatmap) android.view.View.VISIBLE else android.view.View.GONE
        mapStyle?.let { style ->
            style.getLayer(MapStyle.HEATMAP_LAYER)
                ?.setProperties(visibility(if (showHeatmap) Property.VISIBLE else Property.NONE))
            style.getLayer(MapStyle.SHADOW_LAYER)
                ?.setProperties(visibility(if (showHeatmap) Property.NONE else Property.VISIBLE))
        }
    }

    private fun toggleBaseMap() {
        showSatellite = !showSatellite
        updateBaseMap()
    }

    // 위성사진은 기본 지도 위, 라벨 아래에 깔아서 도로명·건물명은 그대로 보이게 한다.
    private fun updateBaseMap() {
        binding.baseMapButton.setText(if (showSatellite) R.string.show_basemap else R.string.show_satellite)
        mapStyle?.getLayer(MapStyle.SATELLITE_LAYER)
            ?.setProperties(visibility(if (showSatellite) Property.VISIBLE else Property.NONE))
        mapStyle?.getLayer(MapStyle.HEATMAP_LAYER)?.setProperties(
            rasterOpacity(if (showSatellite) MapStyle.HEATMAP_OPACITY_ON_SATELLITE else MapStyle.HEATMAP_OPACITY)
        )
    }

    private fun buildLegend() {
        val density = resources.displayMetrics.density
        UtciPalette.legend.forEach { (label, value) ->
            val background = UtciPalette.colorFor(value)
            binding.legend.addView(
                TextView(this).apply {
                    text = label
                    textSize = 10f
                    gravity = Gravity.CENTER
                    setBackgroundColor(background)
                    setTextColor(
                        if (ColorUtils.calculateLuminance(background) > 0.45) 0xFF1F2937.toInt()
                        else 0xFFFFFFFF.toInt()
                    )
                    setPadding(0, (3 * density).toInt(), 0, (3 * density).toInt())
                },
                LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f),
            )
        }
    }

    private fun pickDate() {
        DatePickerDialog(
            this,
            { _, year, month, day ->
                dataDate = LocalDate.of(year, month + 1, day)
                updateDataDateLabel()
                requestForSelectedTime()
            },
            dataDate.year,
            dataDate.monthValue - 1,
            dataDate.dayOfMonth,
        ).apply {
            firstDate?.let { datePicker.minDate = it.toEpochMillis() }
            datePicker.maxDate = defaultDate.toEpochMillis()
        }.show()
    }

    private fun LocalDate.toEpochMillis(): Long = atStartOfDay(SEOUL_ZONE).toInstant().toEpochMilli()

    private fun setToCurrentTime(requestImmediately: Boolean) {
        val now = LocalDateTime.now(SEOUL_ZONE)
        selectedMinutes = (now.hour * 60 + now.minute).coerceIn(START_MINUTES, END_MINUTES)
        binding.timeSlider.progress = selectedMinutes - START_MINUTES
        updateTimeLabel()
        if (requestImmediately) requestForSelectedTime()
    }

    private fun updateTimeLabel() {
        binding.selectedTime.text = getString(
            R.string.selected_time,
            selectedMinutes / 60,
            selectedMinutes % 60,
        )
    }

    private fun updateDataDateLabel(observedAt: LocalDateTime? = null) {
        val date = dataDate.format(DateTimeFormatter.ofPattern("yyyy-MM-dd"))
        binding.dateButton.text = if (dataDate == LocalDate.now(SEOUL_ZONE)) {
            getString(R.string.date_today, date)
        } else {
            date
        }
        binding.dataDateText.text = if (observedAt == null) {
            getString(R.string.data_date, date)
        } else {
            getString(R.string.data_date_observed, date, observedAt.format(HOUR_MINUTE))
        }
    }

    private fun installDataLayers(style: Style) {
        // 위성사진, 그림자, 건물 순으로 쌓고 모두 기본 지도의 라벨 아래에 둔다.
        // 체감온도 히트맵은 첫 응답에서 그림자 아래(위성사진 위)에 추가한다.
        val satelliteTiles = TileSet("2.2.0", BuildConfig.API_BASE_URL + "api/tiles/satellite/{z}/{x}/{y}.jpeg").apply {
            minZoom = MapStyle.SATELLITE_MIN_ZOOM
            maxZoom = MapStyle.SATELLITE_MAX_ZOOM
        }
        style.addSource(RasterSource(MapStyle.SATELLITE_SOURCE, satelliteTiles, 256))
        addBelowLabels(style, RasterLayer(MapStyle.SATELLITE_LAYER, MapStyle.SATELLITE_SOURCE))
        style.addSource(GeoJsonSource(MapStyle.SHADOW_SOURCE, EMPTY_FEATURE_COLLECTION))
        addBelowLabels(
            style,
            FillLayer(MapStyle.SHADOW_LAYER, MapStyle.SHADOW_SOURCE).withProperties(
                fillColor(MapStyle.shadowFillColor),
                fillOpacity(MapStyle.SHADOW_OPACITY),
            )
        )
        val hasHeight = eq(typeOf(get("height_m")), literal("number"))
        style.addSource(GeoJsonSource(MapStyle.BUILDING_SOURCE, EMPTY_FEATURE_COLLECTION))
        addBelowLabels(
            style,
            FillExtrusionLayer(MapStyle.BUILDING_LAYER, MapStyle.BUILDING_SOURCE).withProperties(
                fillExtrusionHeight(coalesce(get("height_m"), literal(MapStyle.UNKNOWN_HEIGHT_M))),
                fillExtrusionBase(0f),
                fillExtrusionColor(
                    switchCase(
                        hasHeight, color(MapStyle.buildingFillColor),
                        color(MapStyle.unknownHeightFillColor),
                    )
                ),
                fillExtrusionOpacity(MapStyle.BUILDING_OPACITY),
            )
        )
        // 경로는 라벨 위에 그려 눈에 띄게 하고, 센서는 그보다 위에 둔다.
        style.addSource(GeoJsonSource(MapStyle.ROUTE_SOURCE, EMPTY_FEATURE_COLLECTION))
        style.addLayer(
            LineLayer(MapStyle.ROUTE_CASING_LAYER, MapStyle.ROUTE_SOURCE).withProperties(
                lineColor(Color.WHITE),
                lineWidth(9f),
                lineCap(Property.LINE_CAP_ROUND),
                lineJoin(Property.LINE_JOIN_ROUND),
            )
        )
        style.addLayer(
            LineLayer(MapStyle.ROUTE_LAYER, MapStyle.ROUTE_SOURCE).withProperties(
                lineColor(
                    match(
                        get("kind"), color(MapStyle.routeShortestColor),
                        stop("balanced", color(MapStyle.routeBalancedColor)),
                        stop("coolest", color(MapStyle.routeCoolestColor)),
                    )
                ),
                lineWidth(5f),
                lineCap(Property.LINE_CAP_ROUND),
                lineJoin(Property.LINE_JOIN_ROUND),
            )
        )
        style.addSource(GeoJsonSource(MapStyle.ROUTE_POINT_SOURCE, EMPTY_FEATURE_COLLECTION))
        style.addLayer(
            CircleLayer(MapStyle.ROUTE_POINT_LAYER, MapStyle.ROUTE_POINT_SOURCE).withProperties(
                circleRadius(8f),
                circleColor(
                    match(get("role"), color(MapStyle.routeEndColor), stop("start", color(MapStyle.routeStartColor)))
                ),
                circleStrokeColor(Color.WHITE),
                circleStrokeWidth(3f),
            )
        )
        // 센서 위치는 다른 모든 층과 라벨 위에 둬서 히트맵·건물에 가리지 않게 한다.
        style.addSource(GeoJsonSource(MapStyle.SENSOR_SOURCE, EMPTY_FEATURE_COLLECTION))
        style.addLayer(
            CircleLayer(MapStyle.SENSOR_LAYER, MapStyle.SENSOR_SOURCE).withProperties(
                circleRadius(MapStyle.SENSOR_RADIUS),
                circleColor(MapStyle.sensorColor),
                circleStrokeColor(Color.WHITE),
                circleStrokeWidth(MapStyle.SENSOR_STROKE_WIDTH),
                circlePitchAlignment(Property.CIRCLE_PITCH_ALIGNMENT_MAP),
            )
        )
        style.addLayer(
            SymbolLayer(MapStyle.SENSOR_LABEL_LAYER, MapStyle.SENSOR_SOURCE).withProperties(
                textField(get("sensor")),
                textFont(MapStyle.labelFont),
                textSize(12f),
                textColor(MapStyle.sensorColor),
                textHaloColor(Color.WHITE),
                textHaloWidth(1.5f),
                textAnchor(Property.TEXT_ANCHOR_TOP),
                textOffset(arrayOf(0f, 0.9f)),
            )
        )
        updateLayerMode()
        updateBaseMap()
    }

    private fun addBelowLabels(style: Style, layer: Layer) {
        val firstLabel = style.layers.firstOrNull { it is SymbolLayer }
        if (firstLabel == null) style.addLayer(layer) else style.addLayerBelow(layer, firstLabel.id)
    }

    private fun showHeatmap(heatmap: UtciHeatmap) {
        val style = mapStyle ?: return
        val source = style.getSourceAs<ImageSource>(MapStyle.HEATMAP_SOURCE)
        if (source == null) {
            style.addSource(ImageSource(MapStyle.HEATMAP_SOURCE, heatmap.quad, heatmap.bitmap))
            style.addLayerBelow(
                RasterLayer(MapStyle.HEATMAP_LAYER, MapStyle.HEATMAP_SOURCE).withProperties(
                    rasterOpacity(MapStyle.HEATMAP_OPACITY),
                    rasterResampling(Property.RASTER_RESAMPLING_LINEAR),
                ),
                MapStyle.SHADOW_LAYER,
            )
            updateLayerMode()
            updateBaseMap()
        } else {
            source.setCoordinates(heatmap.quad)
            source.setImage(heatmap.bitmap)
            updateLayerMode()
        }
    }

    private fun requestBuildings() {
        fetchJson(apiUrl("api/buildings").build(), null) { root ->
            mapStyle?.getSourceAs<GeoJsonSource>(MapStyle.BUILDING_SOURCE)
                ?.setGeoJson(root.toString())
            places = Places.fromBuildings(root)
        }
    }

    private fun requestSensors() {
        fetchJson(apiUrl("api/sensors").build(), null) { root ->
            mapStyle?.getSourceAs<GeoJsonSource>(MapStyle.SENSOR_SOURCE)
                ?.setGeoJson(root.toString())
        }
    }

    private fun requestDataDateThenRefresh() {
        fetchJson(
            apiUrl("api/weather/period").build(),
            null,
            onError = { requestForSelectedTime() },
        ) { root ->
            val latest = OffsetDateTime.parse(root.getString("latest_observation"))
                .atZoneSameInstant(SEOUL_ZONE).toLocalDateTime()
            latestObservation = latest
            firstDate = OffsetDateTime.parse(root.getString("start"))
                .atZoneSameInstant(SEOUL_ZONE).toLocalDate()
            val today = LocalDate.now(SEOUL_ZONE)
            defaultDate = if (root.getBoolean("realtime") && latest.toLocalDate() == today) {
                today
            } else {
                LocalDate.parse(root.getString("latest_full_date"))
            }
            dataDate = defaultDate
            updateDataDateLabel()
            requestForSelectedTime()
        }
    }

    private fun requestForSelectedTime() {
        if (mapStyle == null) return
        if (showHeatmap) requestMicroclimate() else requestShadows()
        // 그늘은 시각마다 달라지므로 경로도 같은 시각으로 다시 구한다.
        requestRoute()
    }

    private fun pickRoutePoint(point: LatLng) {
        val place = Place(getString(R.string.route_map_point), point)
        if (routeStart == null || routeEnd != null) {
            routeStart = place
            routeEnd = null
            showRoute(null)
            binding.routePanel.visibility = android.view.View.VISIBLE
            binding.routeText.text = getString(R.string.route_pick_end)
        } else {
            routeEnd = place
            requestRoute()
        }
        showRouteEnds()
    }

    private fun showRouteDialog() {
        val names = places.map { it.name }
        val padding = (16 * resources.displayMetrics.density).toInt()
        fun field(hint: Int, value: Place?) = AutoCompleteTextView(this).apply {
            setHint(hint)
            threshold = 1
            setAdapter(ArrayAdapter(this@MainActivity, android.R.layout.simple_dropdown_item_1line, names))
            setText(value?.takeIf { it.name in names }?.name.orEmpty())
        }
        val from = field(R.string.route_from, routeStart)
        val to = field(R.string.route_to, routeEnd)
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(padding, padding / 2, padding, 0)
            addView(TextView(this@MainActivity).apply { setText(R.string.route_dialog_hint); textSize = 12f })
            addView(from)
            addView(to)
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.route_dialog_title)
            .setView(content)
            .setNegativeButton(R.string.route_cancel, null)
            .setPositiveButton(R.string.route_find) { _, _ ->
                val start = places.firstOrNull { it.name == from.text.toString().trim() }
                val end = places.firstOrNull { it.name == to.text.toString().trim() }
                val missing = listOf(from to start, to to end).firstOrNull { it.second == null }
                if (missing != null) {
                    Toast.makeText(this, getString(R.string.route_unknown_building, missing.first.text), Toast.LENGTH_LONG).show()
                    return@setPositiveButton
                }
                routeStart = start
                routeEnd = end
                showRouteEnds()
                requestRoute()
            }
            .show()
    }

    private fun requestRoute() {
        val start = routeStart ?: return
        val end = routeEnd ?: return
        if (mapStyle == null) return
        binding.routePanel.visibility = android.view.View.VISIBLE
        binding.routeText.text = getString(R.string.route_loading)
        val url = apiUrl("api/route")
            .addQueryParameter("from_lat", start.point.latitude.toString())
            .addQueryParameter("from_lon", start.point.longitude.toString())
            .addQueryParameter("to_lat", end.point.latitude.toString())
            .addQueryParameter("to_lon", end.point.longitude.toString())
            .addQueryParameter("datetime", selectedDateTime())
            .build()
        routeCall = fetchJson(
            url,
            routeCall,
            onError = { binding.routeText.text = getString(R.string.route_failed); showRoute(null) },
        ) { root ->
            showRoute(root.getJSONObject("routes").toString())
            binding.routeText.text = "${start.name} → ${end.name}\n" + RouteSummary.text(root)
        }
    }

    private fun showRoute(geoJson: String?) {
        mapStyle?.getSourceAs<GeoJsonSource>(MapStyle.ROUTE_SOURCE)?.setGeoJson(geoJson ?: EMPTY_FEATURE_COLLECTION)
    }

    private fun showRouteEnds() {
        mapStyle?.getSourceAs<GeoJsonSource>(MapStyle.ROUTE_POINT_SOURCE)
            ?.setGeoJson(Places.endpointsGeoJson(routeStart, routeEnd))
    }

    private fun clearRoute() {
        routeCall?.cancel()
        routeStart = null
        routeEnd = null
        showRoute(null)
        showRouteEnds()
        binding.routePanel.visibility = android.view.View.GONE
    }

    private fun selectedDateTime(): String =
        dataDate.atTime(selectedMinutes / 60, selectedMinutes % 60)
            .atZone(SEOUL_ZONE)
            .format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)

    private fun requestShadows() {
        shadowCall?.cancel()
        binding.statusText.text = getString(R.string.loading_shadows)
        val url = apiUrl("api/shadows")
            .addQueryParameter("datetime", selectedDateTime())
            .addQueryParameter("lat", CAMPUS_CENTER.latitude.toString())
            .addQueryParameter("lon", CAMPUS_CENTER.longitude.toString())
            .build()
        shadowCall = fetchJson(url, shadowCall) { root ->
            mapStyle?.getSourceAs<GeoJsonSource>(MapStyle.SHADOW_SOURCE)
                ?.setGeoJson(root.getJSONObject("shadows").toString())
            val altitude = root.getJSONObject("solar").getDouble("altitude")
            binding.statusText.text = getString(R.string.solar_altitude, altitude)
        }
    }

    private fun requestMicroclimate() {
        microclimateCall?.cancel()
        binding.statusText.text = getString(R.string.loading_microclimate)
        val url = apiUrl("api/microclimate")
            .addQueryParameter("datetime", selectedDateTime())
            .build()
        microclimateCall = fetchJson(
            url,
            microclimateCall,
            onError = { code -> if (code == 404) showNotObservedYet() },
            parse = UtciHeatmap::fromResponse,
        ) { root, heatmap ->
            showHeatmap(heatmap)
            val observedAt = OffsetDateTime.parse(root.getJSONObject("weather").getString("observed_at"))
                .atZoneSameInstant(SEOUL_ZONE).toLocalDateTime()
            updateDataDateLabel(observedAt)
            val summary = root.getJSONObject("summary")
            val airTemp = root.getJSONObject("weather").getDouble("air_temp_c")
            val sunUp = root.getJSONObject("solar").getDouble("altitude") > 0
            binding.statusText.text = if (sunUp) {
                getString(
                    R.string.utci_summary,
                    airTemp,
                    summary.getDouble("utci_min"),
                    summary.getDouble("utci_max"),
                    summary.getDouble("utci_mean"),
                )
            } else {
                getString(R.string.utci_night, airTemp, summary.getDouble("utci_mean"))
            }
        }
    }

    // The server answers 404 for an instant more than a few hours past its latest
    // observation, i.e. later today than has been observed.
    private fun showNotObservedYet() {
        mapStyle?.getLayer(MapStyle.HEATMAP_LAYER)?.setProperties(visibility(Property.NONE))
        binding.statusText.text = latestObservation?.let {
            getString(R.string.not_observed_yet, it.format(HOUR_MINUTE))
        } ?: getString(R.string.not_observed_yet_unknown)
    }

    private fun apiUrl(path: String): HttpUrl.Builder =
        (BuildConfig.API_BASE_URL + path).toHttpUrl().newBuilder()

    private fun fetchJson(
        url: HttpUrl,
        previous: Call?,
        onError: ((Int?) -> Unit)? = null,
        onSuccess: (JSONObject) -> Unit,
    ): Call = fetchJson(url, previous, onError, parse = { }) { root, _ -> onSuccess(root) }

    /**
     * GET [url] and hand the parsed body to [onSuccess] on the UI thread. [parse]
     * runs on the network thread first, for work such as building a bitmap.
     * [onError] gets the HTTP status, or null when the request never got one.
     */
    private fun <T> fetchJson(
        url: HttpUrl,
        previous: Call?,
        onError: ((Int?) -> Unit)? = null,
        parse: (JSONObject) -> T,
        onSuccess: (JSONObject, T) -> Unit,
    ): Call {
        previous?.cancel()
        val call = client.newCall(Request.Builder().url(url).build())
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, error: IOException) {
                if (call.isCanceled()) return
                runOnUiThread {
                    binding.statusText.text = getString(R.string.network_error, error.localizedMessage)
                    onError?.invoke(null)
                }
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    if (!it.isSuccessful) {
                        runOnUiThread {
                            binding.statusText.text = getString(R.string.http_error, it.code)
                            onError?.invoke(it.code)
                        }
                        return
                    }
                    val root = JSONObject(it.body?.string().orEmpty())
                    val parsed = parse(root)
                    if (!call.isCanceled()) runOnUiThread { onSuccess(root, parsed) }
                }
            }
        })
        return call
    }

    override fun onStart() { super.onStart(); binding.mapView.onStart() }
    override fun onResume() { super.onResume(); binding.mapView.onResume() }
    override fun onPause() { binding.mapView.onPause(); super.onPause() }
    override fun onStop() { binding.mapView.onStop(); super.onStop() }
    override fun onLowMemory() { super.onLowMemory(); binding.mapView.onLowMemory() }
    override fun onDestroy() {
        shadowCall?.cancel()
        microclimateCall?.cancel()
        routeCall?.cancel()
        handler.removeCallbacksAndMessages(null)
        binding.mapView.onDestroy()
        super.onDestroy()
    }
    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        binding.mapView.onSaveInstanceState(outState)
    }

    companion object {
        private val CAMPUS_CENTER = LatLng(36.6268, 127.4583)
        private val SEOUL_ZONE = ZoneId.of("Asia/Seoul")
        private val HOUR_MINUTE = DateTimeFormatter.ofPattern("HH:mm")
        private const val START_MINUTES = 6 * 60
        private const val END_MINUTES = 20 * 60
        private const val EMPTY_FEATURE_COLLECTION =
            "{\"type\":\"FeatureCollection\",\"features\":[]}"
    }
}
