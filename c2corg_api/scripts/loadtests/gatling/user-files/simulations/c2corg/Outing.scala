package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._

object Outing {
  val feeder = csv("outings.csv").random

  val header_search = Map(
    "Accept" -> "application/json, text/javascript, */*; q=0.01",
    "Origin" -> C2corgConf.ui_url)

  val view = feed(feeder).exec(
    http("View outing")
      .get("/outings/${id}/${lang}/foo")
      .headers(C2corgConf.header_html)
      .basicAuth(C2corgConf.basic_auth_username, C2corgConf.basic_auth_password)
  )

  val add = exec(
    http("Creating an outing")
      .get("/outings/add")
      .headers(C2corgConf.header_html)
      .basicAuth(C2corgConf.basic_auth_username, C2corgConf.basic_auth_password)
    )
    .pause(14)
    .exec(http("Associating a route")
            .get(C2corgConf.api_url + "/search?q=grange&pl=fr&t=r")
            .headers(header_search)
    )
    .pause(20)
    .exec(
      http("Saving new outing")
        .post(C2corgConf.api_url + "/outings")
        .headers(Auth.header_authorization_data)
        .body(RawFileBody("new_outing_data.txt"))
        .check(
          jsonPath("$.document_id").exists.saveAs("new_outing_id")
        )
    )
    .pause(500 milliseconds)
    .exec(
      http("View created outing")
        .get(C2corgConf.ui_url + "/outings/${new_outing_id}/fr/foo")
        .headers(C2corgConf.header_html)
        .basicAuth(C2corgConf.basic_auth_username, C2corgConf.basic_auth_password)
    )
}
