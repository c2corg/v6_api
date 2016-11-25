package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._

object Image {

  // routes the test image will be associated to
  val feeder = csv("routes.csv").random

  val header_upload = Map(
    "Accept" -> "application/json, text/plain, */*",
    "Content-Type" -> "multipart/form-data; boundary=---------------------------166432501311328536621127374949",
    "Origin" -> C2corgConf.ui_url)

  val upload = feed(feeder).exec(
    http("Uploading an image")
      .post(C2corgConf.image_url + "/upload")
      .headers(header_upload)
      .body(RawFileBody("image_file.txt"))
      .check(
        jsonPath("$.filename").exists.saveAs("filename")
      )
  )
  .pause(8)
  .exec(
    http("Saving image in API")
    .post(C2corgConf.api_url + "/images/list")
    .headers(Auth.header_authorization_data)
    .body(StringBody("""{ "images": [{ "id": "monalisa.jpg-2016-11-22T13:17:46.271Z", "activities": [], "categories": [], "image_type": "collaborative", "elevation": null, "geometry": {}, "Orientation": "top-left", "XResolution": "72", "YResolution": "72", "ResolutionUnit": "2", "Software": "GIMP 2.8.16", "DateTime": "2016:11:22 14:16:20", "ExifIFDPointer": "146", "ExifVersion": "0210", "FlashpixVersion": "0100", "ColorSpace": "65535", "PixelXDimension": "2013", "PixelYDimension": "3000", "title": "La Joconde", "filename": "${filename}", "file_size": 1879430, "associations": { "routes": [{ "document_id": ${id} }]}, "locales": [{ "lang": "fr", "title": "La Joconde" }], "date_time": "2016-11-22", "camera_name": null }] }""")).asJSON
    .check(
      status.is(200)
    )
  )
  .pause(500 milliseconds)
  .exec(
    http("Show route with new image")
      .get(C2corgConf.ui_url + "/routes/${id}/${lang}/foo")
      .headers(C2corgConf.header_html)
      .basicAuth(C2corgConf.basic_auth_username, C2corgConf.basic_auth_password)
  )
}
