package c2corg

import io.gatling.core.Predef._

object C2corgConf {

  val ui_url = "http://www.gatling.camptocamp.org"
  val api_url = "http://api.gatling.camptocamp.org"
  val forum_url = "http://forum.gatling.camptocamp.org"
  val image_url = "http://images.gatling.camptocamp.org"

  val header_json = Map("Accept" -> "application/json", "Origin" -> ui_url)

  val header_html = Map("Accept" -> "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")

  val header_discourse_1 = Map(
    "Discourse-Track-View" -> "true",
    "X-CSRF-Token" -> "undefined",
    "X-Requested-With" -> "XMLHttpRequest")

  val header_discourse_2 = Map(
    "X-CSRF-Token" -> "undefined",
    "X-Requested-With" -> "XMLHttpRequest")

  val basic_auth_username = "c2corg"
  val basic_auth_password = "c2corg"

  val black_list = BlackList("""http://server1.affiz.net/.*""", """https://www.google-analytics.com/analytics.js""", """https://www.google.com/recaptcha/api.js?.*""", """http://sos.exo.io/.*""", """http://api.geonames.org/searchJSON""", """.*/static/.*""", """.*/images/proxy/.*""", """http://i.imgur.com/.*""", """.*.ico""", """.*css.*""", """.*.js""")

}
