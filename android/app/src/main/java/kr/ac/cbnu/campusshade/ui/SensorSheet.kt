package kr.ac.cbnu.campusshade.ui

import android.view.View
import android.view.ViewGroup
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.bottomsheet.BottomSheetDialog
import kr.ac.cbnu.campusshade.SensorInfo
import kr.ac.cbnu.campusshade.SensorSite
import kr.ac.cbnu.campusshade.databinding.ItemInfoRowBinding
import kr.ac.cbnu.campusshade.databinding.SheetSensorBinding

/** The bottom sheet a tapped sensor opens: its latest reading (none yet) and the site. */
class SensorSheet(private val activity: AppCompatActivity) {
    private val sheet = SheetSensorBinding.inflate(activity.layoutInflater)
    private val dialog = BottomSheetDialog(activity).apply { setContentView(sheet.root) }

    fun show(site: SensorSite) {
        sheet.sensorTitle.text = site.name
        // 측정값 API가 생기면 여기서 SensorReading을 넘기면 된다.
        fillInfoRows(sheet.sensorReadingRows, SensorInfo.readingRows(null))
        sheet.sensorReadingNote.visibility = View.VISIBLE
        fillInfoRows(sheet.sensorSiteRows, SensorInfo.siteRows(site))
        dialog.show()
    }

    fun dismiss() = dialog.dismiss()

    private fun fillInfoRows(container: ViewGroup, rows: List<Pair<String, String>>) {
        container.removeAllViews()
        rows.forEach { (label, value) ->
            val row = ItemInfoRowBinding.inflate(activity.layoutInflater, container, true)
            row.infoLabel.text = label
            row.infoValue.text = value
        }
    }
}
