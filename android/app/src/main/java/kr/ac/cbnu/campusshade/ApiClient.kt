package kr.ac.cbnu.campusshade

import android.app.Activity
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import org.json.JSONObject
import java.io.IOException

/**
 * GETs JSON from the campus API off the UI thread. Errors go to [showStatus]
 * (the status line) unless a call asks otherwise.
 */
class ApiClient(private val activity: Activity, private val showStatus: (String) -> Unit) {
    private val client = OkHttpClient()

    fun url(path: String): HttpUrl.Builder =
        (BuildConfig.API_BASE_URL + path).toHttpUrl().newBuilder()

    fun fetchJson(
        url: HttpUrl,
        previous: Call?,
        onError: ((Int?) -> Unit)? = null,
        reportErrors: Boolean = true,
        onSuccess: (JSONObject) -> Unit,
    ): Call = fetchJson(url, previous, onError, reportErrors, parse = { }) { root, _ -> onSuccess(root) }

    /**
     * GET [url] and hand the parsed body to [onSuccess] on the UI thread. [parse]
     * runs on the network thread first, for work such as building a bitmap.
     * [onError] gets the HTTP status, or null when the request never got one.
     * Errors are also shown in the status line unless [reportErrors] is false.
     */
    fun <T> fetchJson(
        url: HttpUrl,
        previous: Call?,
        onError: ((Int?) -> Unit)? = null,
        reportErrors: Boolean = true,
        parse: (JSONObject) -> T,
        onSuccess: (JSONObject, T) -> Unit,
    ): Call {
        previous?.cancel()
        val call = client.newCall(Request.Builder().url(url).build())
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, error: IOException) {
                if (call.isCanceled()) return
                activity.runOnUiThread {
                    if (reportErrors) showStatus(activity.getString(R.string.network_error, error.localizedMessage))
                    onError?.invoke(null)
                }
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    if (!it.isSuccessful) {
                        activity.runOnUiThread {
                            if (reportErrors) showStatus(activity.getString(R.string.http_error, it.code))
                            onError?.invoke(it.code)
                        }
                        return
                    }
                    val root = JSONObject(it.body?.string().orEmpty())
                    val parsed = parse(root)
                    if (!call.isCanceled()) activity.runOnUiThread { onSuccess(root, parsed) }
                }
            }
        })
        return call
    }
}
