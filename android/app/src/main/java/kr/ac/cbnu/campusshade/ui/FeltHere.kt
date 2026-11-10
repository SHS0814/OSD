package kr.ac.cbnu.campusshade.ui

import android.view.View
import androidx.appcompat.app.AppCompatActivity
import kr.ac.cbnu.campusshade.FeltStage
import kr.ac.cbnu.campusshade.R
import kr.ac.cbnu.campusshade.databinding.ActivityMainBinding
import kotlin.math.roundToInt

/** The screen edge tinted by the felt temperature where you stand, and its "내 위치 체감" line. */
class FeltHere(private val activity: AppCompatActivity, private val binding: ActivityMainBinding) {
    /** [utci] there, or null for no effect (not now, not on campus, or no location). */
    fun show(utci: Double?) {
        if (utci == null) {
            binding.feltEdge.setStage(FeltStage.COMFORT)
            binding.feltCard.visibility = View.GONE
            return
        }
        binding.feltEdge.setStage(FeltStage.of(utci))
        binding.feltText.text = activity.getString(R.string.felt_here, utci.roundToInt(), FeltStage.label(utci))
        binding.feltCard.visibility = View.VISIBLE
    }
}
