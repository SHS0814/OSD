package kr.ac.cbnu.campusshade.map

import org.maplibre.android.style.layers.Layer
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.layers.PropertyFactory.visibility
import org.maplibre.android.style.layers.SymbolLayer
import org.maplibre.android.maps.Style

const val EMPTY_FEATURE_COLLECTION = "{\"type\":\"FeatureCollection\",\"features\":[]}"

/** Adds [layer] under the base map's first label layer, so its names stay readable. */
internal fun Style.addBelowLabels(layer: Layer) {
    val firstLabel = layers.firstOrNull { it is SymbolLayer }
    if (firstLabel == null) addLayer(layer) else addLayerBelow(layer, firstLabel.id)
}

internal fun visibleIf(shown: Boolean) = visibility(if (shown) Property.VISIBLE else Property.NONE)
