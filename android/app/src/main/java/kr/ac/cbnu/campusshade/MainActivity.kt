package kr.ac.cbnu.campusshade

import android.app.DatePickerDialog
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import androidx.activity.SystemBarStyle
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import kr.ac.cbnu.campusshade.databinding.ActivityMainBinding
import kr.ac.cbnu.campusshade.map.MapLayers
import kr.ac.cbnu.campusshade.ui.Legend
import kr.ac.cbnu.campusshade.ui.MapSettingsSheet
import kr.ac.cbnu.campusshade.ui.RouteCard
import kr.ac.cbnu.campusshade.ui.SearchPanel
import kr.ac.cbnu.campusshade.ui.TimeSheet
import okhttp3.Call
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.Style
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * The one screen. It keeps what has been chosen (time, layers, route ends,
 * where you are) and asks the API; the map layers (map/) draw the answers and
 * the panels (ui/) show them and report what the user picks.
 */
class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private lateinit var api: ApiClient
    // 시각 선택과 지도 설정은 바텀시트에 담는다. 한 번 만들어 두고 다시 연다.
    private lateinit var timeSheet: TimeSheet
    private lateinit var mapSettings: MapSettingsSheet
    private lateinit var search: SearchPanel
    private lateinit var routeCard: RouteCard
    private lateinit var legend: Legend
    private val handler = Handler(Looper.getMainLooper())
    private var map: MapLibreMap? = null
    private var mapStyle: Style? = null
    private var layers: MapLayers? = null
    private var shadowCall: Call? = null
    private var microclimateCall: Call? = null
    private var selectedMinutes = 14 * 60
    // 시각 카드의 "현재 시각"/"선택 시각": 날짜나 시각을 직접 고르면 false
    private var followingNow = true
    private var is3d = true
    private var showHeatmap = true
    private var showSatellite = true
    private var sensors: List<SensorSite> = emptyList()

    // 길찾기: 출발지·도착지(검색한 건물 또는 지도에서 길게 누른 곳)
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
        // 지도는 상태바·내비게이션바 아래까지 그리고, 밝은 지도 위라 바 아이콘은 어둡게 둔다.
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT),
        )
        super.onCreate(savedInstanceState)
        MapLibre.getInstance(this)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        // 지도는 화면 끝까지 채우고, 떠 있는 컨트롤만 시스템 바와 화면 컷아웃을 피한다.
        ViewCompat.setOnApplyWindowInsetsListener(binding.overlay) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }
        binding.mapView.onCreate(savedInstanceState)

        api = ApiClient(this) { binding.statusText.text = it }
        timeSheet = TimeSheet(this, binding)
        mapSettings = MapSettingsSheet(this)
        search = SearchPanel(this, binding)
        routeCard = RouteCard(binding)
        legend = Legend(binding.legend)

        setToCurrentTime(requestImmediately = false)
        configureControls()
        configureSearch()
        updateDataDateLabel()
        binding.mapView.getMapAsync { mapLibreMap ->
            map = mapLibreMap
            mapLibreMap.cameraPosition = CameraPosition.Builder()
                .target(CAMPUS_CENTER)
                .zoom(16.2)
                .tilt(MapStyle.TILT_3D)
                .build()
            // 저작권 표시는 아래 카드에 모아 둔다.
            mapLibreMap.uiSettings.isLogoEnabled = false
            mapLibreMap.uiSettings.isAttributionEnabled = false
            mapLibreMap.addOnMapLongClickListener { point -> search.hideResults(); pickRoutePoint(point); true }
            mapLibreMap.addOnMapClickListener { point -> onMapTapped(point) }
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
        timeSheet.onSlide = { progress, fromUser ->
            selectedMinutes = START_MINUTES + progress
            if (fromUser) followingNow = false
            updateTimeLabel()
            if (fromUser) {
                handler.removeCallbacks(debounceRequest)
                handler.postDelayed(debounceRequest, 400)
            }
        }
        timeSheet.onNow = {
            dataDate = defaultDate
            setToCurrentTime(requestImmediately = true)
            updateDataDateLabel()
        }
        timeSheet.onPickDate = { pickDate() }

        binding.mapSettingsButton.setOnClickListener { mapSettings.show() }
        mapSettings.on3dPicked = { if (it != is3d) toggleViewMode() }
        mapSettings.onSatellitePicked = { if (it != showSatellite) toggleBaseMap() }
        mapSettings.onHeatmapPicked = { if (it != showHeatmap) toggleLayerMode() }
        routeCard.onClear = { clearRoute() }
        updateViewModeButton()
        updateLayerMode()
        updateBaseMapButton()
    }

    private fun toggleViewMode() {
        is3d = !is3d
        val tilt = if (is3d) MapStyle.TILT_3D else 0.0
        map?.animateCamera(CameraUpdateFactory.tiltTo(tilt), 600)
        updateViewModeButton()
    }

    private fun updateViewModeButton() = mapSettings.show3d(is3d)

    // The heatmap already accounts for shade, so it replaces the shadow layer
    // instead of being drawn on top of it.
    private fun toggleLayerMode() {
        showHeatmap = !showHeatmap
        updateLayerMode()
        requestForSelectedTime()
    }

    private fun updateLayerMode() {
        mapSettings.showHeatmap(showHeatmap)
        legend.setVisible(showHeatmap)
        layers?.let {
            it.heatmap.setVisible(showHeatmap)
            it.shadows.setVisible(!showHeatmap)
        }
    }

    private fun toggleBaseMap() {
        showSatellite = !showSatellite
        updateBaseMap()
    }

    private fun updateBaseMapButton() = mapSettings.showSatellite(showSatellite)

    // 위성사진은 기본 지도 위, 라벨 아래에 깔아서 도로명·건물명은 그대로 보이게 한다.
    private fun updateBaseMap() {
        updateBaseMapButton()
        layers?.satellite?.setVisible(showSatellite)
        layers?.heatmap?.setOverSatellite(showSatellite)
    }

    private fun pickDate() {
        DatePickerDialog(
            this,
            { _, year, month, day ->
                dataDate = LocalDate.of(year, month + 1, day)
                followingNow = false
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
        followingNow = true
        timeSheet.setProgress(selectedMinutes - START_MINUTES)
        updateTimeLabel()
        if (requestImmediately) requestForSelectedTime()
    }

    private fun updateTimeLabel() {
        timeSheet.showSelectedTime(selectedMinutes)
        updateTimeCard()
    }

    private fun updateTimeCard() {
        timeSheet.showCard(followingNow, selectedMinutes, dataDate, LocalDate.now(SEOUL_ZONE))
    }

    private fun updateDataDateLabel(observedAt: LocalDateTime? = null) {
        timeSheet.showDataDate(dataDate, LocalDate.now(SEOUL_ZONE), observedAt)
        updateTimeCard()
    }

    // ---- 건물 검색 ----

    private fun configureSearch() {
        search.onFocus = { building ->
            map?.animateCamera(CameraUpdateFactory.newLatLngZoom(building.latLng(), SELECTED_ZOOM), 700)
        }
        search.onRouteEnd = { building, start -> useBuildingAsRouteEnd(building, start) }
    }

    private fun Building.latLng() = LatLng(latitude, longitude)

    // ---- 지도 누르기 ----

    private fun onMapTapped(point: LatLng): Boolean {
        // 검색 결과가 열려 있으면 첫 탭은 닫기만 한다.
        if (search.isShowingResults) {
            search.hideResults()
            return true
        }
        return false
    }

    // ---- 길찾기 ----

    private fun useBuildingAsRouteEnd(building: Building, start: Boolean) {
        val place = Place(building.label, building.latLng())
        if (start) routeStart = place else routeEnd = place
        search.hideSelection()
        onRouteEndsChanged()
    }

    private fun pickRoutePoint(point: LatLng) {
        val place = Place(getString(R.string.route_map_point), point)
        when {
            // 이미 경로가 있으면 새 출발지부터 다시 고른다.
            routeStart != null && routeEnd != null -> { routeStart = place; routeEnd = null }
            routeStart == null -> routeStart = place
            else -> routeEnd = place
        }
        onRouteEndsChanged()
    }

    // 출발·도착이 다 정해지면 경로를 구하고, 하나만 있으면 나머지를 고르라고 안내한다.
    private fun onRouteEndsChanged() {
        showRouteEnds()
        val start = routeStart
        val end = routeEnd
        if (start != null && end != null) {
            requestRoute()
            return
        }
        routeCall?.cancel()
        showRoute(null)
        routeCard.showOrHide(
            when {
                start != null -> getString(R.string.route_pick_end, start.name)
                end != null -> getString(R.string.route_pick_start, end.name)
                else -> ""
            }
        )
    }

    // ---- 지도 데이터 ----

    private fun installDataLayers(style: Style) {
        layers = MapLayers(style, this)
        updateLayerMode()
        updateBaseMap()
    }

    private fun showHeatmap(heatmap: UtciHeatmap) {
        val layers = layers ?: return
        if (layers.heatmap.show(heatmap)) {
            updateLayerMode()
            updateBaseMap()
        } else {
            updateLayerMode()
        }
    }

    private fun requestBuildings() {
        api.fetchJson(api.url("api/buildings").build(), null) { root ->
            layers?.buildings?.show(root.toString())
            search.buildings = Places.buildings(root)
        }
    }

    private fun requestSensors() {
        api.fetchJson(api.url("api/sensors").build(), null) { root ->
            layers?.sensors?.show(root.toString())
            sensors = Places.sensors(root)
        }
    }

    private fun requestDataDateThenRefresh() {
        api.fetchJson(
            api.url("api/weather/period").build(),
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

    private fun requestRoute() {
        val start = routeStart ?: return
        val end = routeEnd ?: return
        if (mapStyle == null) return
        routeCard.show(getString(R.string.route_loading))
        val url = api.url("api/route")
            .addQueryParameter("from_lat", start.point.latitude.toString())
            .addQueryParameter("from_lon", start.point.longitude.toString())
            .addQueryParameter("to_lat", end.point.latitude.toString())
            .addQueryParameter("to_lon", end.point.longitude.toString())
            .addQueryParameter("datetime", selectedDateTime())
            .build()
        routeCall = api.fetchJson(
            url,
            routeCall,
            onError = { routeCard.setText(getString(R.string.route_failed)); showRoute(null) },
        ) { root ->
            showRoute(root.getJSONObject("routes").toString())
            routeCard.setText("${start.name} → ${end.name}\n" + RouteSummary.text(root))
        }
    }

    private fun showRoute(geoJson: String?) {
        layers?.routes?.showRoutes(geoJson)
    }

    private fun showRouteEnds() {
        layers?.routes?.showEnds(routeStart, routeEnd)
    }

    private fun clearRoute() {
        routeCall?.cancel()
        routeStart = null
        routeEnd = null
        showRoute(null)
        showRouteEnds()
        routeCard.hide()
    }

    private fun selectedDateTime(): String =
        dataDate.atTime(selectedMinutes / 60, selectedMinutes % 60)
            .atZone(SEOUL_ZONE)
            .format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)

    private fun requestShadows() {
        shadowCall?.cancel()
        binding.statusText.text = getString(R.string.loading_shadows)
        val url = api.url("api/shadows")
            .addQueryParameter("datetime", selectedDateTime())
            .addQueryParameter("lat", CAMPUS_CENTER.latitude.toString())
            .addQueryParameter("lon", CAMPUS_CENTER.longitude.toString())
            .build()
        shadowCall = api.fetchJson(url, shadowCall) { root ->
            layers?.shadows?.show(root.getJSONObject("shadows").toString())
            val altitude = root.getJSONObject("solar").getDouble("altitude")
            binding.statusText.text = getString(R.string.solar_altitude, altitude)
        }
    }

    private fun requestMicroclimate() {
        microclimateCall?.cancel()
        binding.statusText.text = getString(R.string.loading_microclimate)
        val url = api.url("api/microclimate")
            .addQueryParameter("datetime", selectedDateTime())
            .build()
        microclimateCall = api.fetchJson(
            url,
            microclimateCall,
            onError = { code ->
                if (code == 404) showNotObservedYet()
            },
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
        layers?.heatmap?.setVisible(false)
        binding.statusText.text = latestObservation?.let {
            getString(R.string.not_observed_yet, it.format(HOUR_MINUTE))
        } ?: getString(R.string.not_observed_yet_unknown)
    }

    override fun onStart() {
        super.onStart()
        binding.mapView.onStart()
    }
    override fun onResume() { super.onResume(); binding.mapView.onResume() }
    override fun onPause() { binding.mapView.onPause(); super.onPause() }
    override fun onStop() { binding.mapView.onStop(); super.onStop() }
    override fun onLowMemory() { super.onLowMemory(); binding.mapView.onLowMemory() }
    override fun onDestroy() {
        shadowCall?.cancel()
        microclimateCall?.cancel()
        routeCall?.cancel()
        timeSheet.dismiss()
        mapSettings.dismiss()
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
        private const val SELECTED_ZOOM = 17.5
        private const val START_MINUTES = 6 * 60
        private const val END_MINUTES = 20 * 60
    }
}
