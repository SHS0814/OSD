package kr.ac.cbnu.campusshade.ui

import android.view.View
import kr.ac.cbnu.campusshade.databinding.ActivityMainBinding

/** The route lines in the info card: what is being asked, then the comparison of the routes. */
class RouteCard(private val binding: ActivityMainBinding) {
    var onClear: () -> Unit = {}

    init {
        binding.clearRouteButton.setOnClickListener { onClear() }
    }

    fun show(text: String) {
        binding.routePanel.visibility = View.VISIBLE
        binding.routeText.text = text
    }

    /** Shows the panel only while [text] is not empty. */
    fun showOrHide(text: String) {
        binding.routePanel.visibility = if (text.isEmpty()) View.GONE else View.VISIBLE
        binding.routeText.text = text
    }

    fun setText(text: String) {
        binding.routeText.text = text
    }

    fun hide() {
        binding.routePanel.visibility = View.GONE
    }
}
