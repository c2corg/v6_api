package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._

object Forum {

  val feeder = csv("forums.csv").random

  val init = exec(
    http("Forum init")
      .get("/")
      .headers(C2corgConf.header_html)
      .resources(
        http("Forum categories")
          .get("/categories_and_latest?")
          .headers(C2corgConf.header_discourse_1)
      )
  )

  val open = feed(feeder).exec(
    http("Open forum")
      .get("/c/${forum_name}/l/latest.json")
      .headers(C2corgConf.header_discourse_1)
  )

  val scroll = feed(feeder).exec(
    http("Scroll forum")
      .get("/c/${forum_name}/l/latest")
      .headers(C2corgConf.header_discourse_2)
  )
}

