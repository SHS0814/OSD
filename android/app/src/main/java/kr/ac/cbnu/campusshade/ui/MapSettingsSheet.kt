package kr.ac.cbnu.campusshade.ui

import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.bottomsheet.BottomSheetDialog
import kr.ac.cbnu.campusshade.R
import kr.ac.cbnu.campusshade.databinding.SheetMapSettingsBinding

/**
 * The map settings bottom sheet: 3D/2D, satellite/plain base map,
 * heatmap/shadows, wind arrows and sensor sites. Each choice is reported as
 * the value the user picked; showing a value changes the buttons only.
 */
class MapSettingsSheet(activity: AppCompatActivity) {
    private val sheet = SheetMapSettingsBinding.inflate(activity.layoutInflater)
    private val dialog = BottomSheetDialog(activity).apply { setContentView(sheet.root) }

    var on3dPicked: (Boolean) -> Unit = {}
    var onSatellitePicked: (Boolean) -> Unit = {}
    var onHeatmapPicked: (Boolean) -> Unit = {}
    var onSensorsPicked: (Boolean) -> Unit = {}

    init {
        sheet.viewModeGroup.addOnButtonCheckedListener { _, id, checked ->
            if (checked) on3dPicked(id == R.id.viewMode3d)
        }
        sheet.baseMapGroup.addOnButtonCheckedListener { _, id, checked ->
            if (checked) onSatellitePicked(id == R.id.baseMapSatellite)
        }
        sheet.layerModeGroup.addOnButtonCheckedListener { _, id, checked ->
            if (checked) onHeatmapPicked(id == R.id.layerHeatmap)
        }
        sheet.sensorGroup.addOnButtonCheckedListener { _, id, checked ->
            if (checked) onSensorsPicked(id == R.id.sensorsOn)
        }
    }

    fun show() = dialog.show()

    fun dismiss() = dialog.dismiss()

    fun show3d(is3d: Boolean) = sheet.viewModeGroup.check(if (is3d) R.id.viewMode3d else R.id.viewMode2d)

    fun showSatellite(satellite: Boolean) =
        sheet.baseMapGroup.check(if (satellite) R.id.baseMapSatellite else R.id.baseMapNormal)

    fun showHeatmap(heatmap: Boolean) = sheet.layerModeGroup.check(if (heatmap) R.id.layerHeatmap else R.id.layerShadow)

    fun showSensors(sensors: Boolean) = sheet.sensorGroup.check(if (sensors) R.id.sensorsOn else R.id.sensorsOff)
}
